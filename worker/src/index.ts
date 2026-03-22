import { McpAgent } from "agents/mcp";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { z } from "zod";

import { OctivClient, type Env } from "./octiv";
import { formatSchedule, formatWod, weekBounds } from "./format";

export { Env };

// ── MCP Agent (runs inside a Durable Object) ──────────────────────────────────

export class OctivMCP extends McpAgent<Env> {
  server = new McpServer({ name: "octiv", version: "1.0.0" });
  private client!: OctivClient;

  async init() {
    this.client = new OctivClient(this.env);
    this.registerTools();
  }

  private registerTools() {
    // ── get_weekly_schedule ───────────────────────────────────────────────────
    this.server.tool(
      "get_weekly_schedule",
      "Fetch the full class schedule for the current week (Monday–Sunday) from Octiv Fitness. " +
        "Shows all classes with times, instructor, capacity, and whether you are booked in.",
      {
        week_offset: z
          .number()
          .int()
          .optional()
          .describe("0 = current week, 1 = next week, -1 = last week. Defaults to 0."),
      },
      async ({ week_offset }) => {
        const me = await this.client.getMe();
        const myUserId = me["id"] as number | undefined;
        const [start, end] = weekBounds(week_offset ?? 0);
        const raw = await this.client.getClassDates(start, end);
        const schedule = formatSchedule(raw, myUserId);
        const [tenantId, locationId] = this.client.extractGymIds(me);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  week: `${start} to ${end}`,
                  gym: { tenantId, locationId },
                  totalClasses: schedule.length,
                  classes: schedule,
                },
                null,
                2
              ),
            },
          ],
        };
      }
    );

    // ── get_schedule_for_date ─────────────────────────────────────────────────
    this.server.tool(
      "get_schedule_for_date",
      "Fetch the class schedule for a specific date or date range from Octiv Fitness.",
      {
        start_date: z.string().describe("Start date in YYYY-MM-DD format."),
        end_date: z
          .string()
          .optional()
          .describe(
            "End date in YYYY-MM-DD format. If omitted, defaults to start_date (single day)."
          ),
      },
      async ({ start_date, end_date }) => {
        const me = await this.client.getMe();
        const myUserId = me["id"] as number | undefined;
        const end = end_date ?? start_date;
        const raw = await this.client.getClassDates(start_date, end);
        const schedule = formatSchedule(raw, myUserId);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  dateRange: start_date !== end ? `${start_date} to ${end}` : start_date,
                  totalClasses: schedule.length,
                  classes: schedule,
                },
                null,
                2
              ),
            },
          ],
        };
      }
    );

    // ── get_my_bookings ───────────────────────────────────────────────────────
    this.server.tool(
      "get_my_bookings",
      "Fetch the classes you are personally booked into for a given date range. " +
        "Defaults to the next 7 days if no dates are provided.",
      {
        start_date: z
          .string()
          .optional()
          .describe("Start date in YYYY-MM-DD format. Defaults to today."),
        end_date: z
          .string()
          .optional()
          .describe("End date in YYYY-MM-DD format. Defaults to 7 days from start."),
      },
      async ({ start_date, end_date }) => {
        const today = new Date();
        const start = start_date ?? today.toISOString().split("T")[0];
        const defaultEnd = new Date(today);
        defaultEnd.setDate(today.getDate() + 6);
        const end = end_date ?? defaultEnd.toISOString().split("T")[0];

        const me = await this.client.getMe();
        const myUserId = me["id"] as number | undefined;
        const raw = await this.client.getClassDates(start, end);
        const allClasses = formatSchedule(raw, myUserId);
        const myClasses = allClasses.filter((c) => "myBooking" in c);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  dateRange: `${start} to ${end}`,
                  myBookingsCount: myClasses.length,
                  bookings: myClasses,
                },
                null,
                2
              ),
            },
          ],
        };
      }
    );

    // ── get_programmes ────────────────────────────────────────────────────────
    this.server.tool(
      "get_programmes",
      "List all available training programmes for your gym. " +
        "Use this to discover programme IDs (e.g. to pass to get_wod).",
      {},
      async () => {
        const raw = await this.client.getProgrammes();
        const programmes = ((raw["data"] as Record<string, unknown>[]) ?? []).map((p) => ({
          id: p["id"],
          name: p["name"],
          description: p["description"],
        }));

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify({ total: programmes.length, programmes }, null, 2),
            },
          ],
        };
      }
    );

    // ── get_wod ───────────────────────────────────────────────────────────────
    this.server.tool(
      "get_wod",
      "Fetch the Workout of the Day (WOD) from Octiv Fitness for a specific date or date range. " +
        "Returns the warm-up, exercises (with descriptions and measuring units), and cool-down. " +
        "If no programme is specified and OCTIV_PROGRAMME_IDS is not set, " +
        "returns the available programmes so the user can choose one.",
      {
        date: z
          .string()
          .optional()
          .describe("Date in YYYY-MM-DD format. Defaults to today."),
        end_date: z
          .string()
          .optional()
          .describe(
            "Inclusive end date in YYYY-MM-DD format for a multi-day range. Defaults to date (single day)."
          ),
        programme_ids: z
          .string()
          .optional()
          .describe(
            "Comma-separated programme IDs to filter by. " +
              "If omitted, falls back to OCTIV_PROGRAMME_IDS env var. " +
              "If neither is set, available programmes are returned instead. " +
              "Use get_programmes to discover available IDs."
          ),
      },
      async ({ date, end_date, programme_ids }) => {
        const today = new Date().toISOString().split("T")[0];
        const dateStr = date ?? today;
        const endInclusive = end_date ?? dateStr;

        // WOD API uses exclusive upper bound — add one day
        const exclusiveEnd = new Date(endInclusive);
        exclusiveEnd.setDate(exclusiveEnd.getDate() + 1);
        const endExclusive = exclusiveEnd.toISOString().split("T")[0];

        const pids = programme_ids ?? this.env.OCTIV_PROGRAMME_IDS;

        if (!pids) {
          // Guide the user to pick a programme
          const rawProgrammes = await this.client.getProgrammes();
          const programmes = ((rawProgrammes["data"] as Record<string, unknown>[]) ?? []).map(
            (p) => ({ id: p["id"], name: p["name"], description: p["description"] })
          );
          return {
            content: [
              {
                type: "text",
                text: JSON.stringify(
                  {
                    action: "select_programme",
                    message:
                      "No programme selected. " +
                      "Please choose one of the available programmes and re-ask for the WOD.",
                    availableProgrammes: programmes,
                  },
                  null,
                  2
                ),
              },
            ],
          };
        }

        const raw = await this.client.getWods(dateStr, endExclusive, pids);
        const wods = formatWod(raw);

        return {
          content: [
            {
              type: "text",
              text: JSON.stringify(
                {
                  dateRange:
                    endInclusive !== dateStr ? `${dateStr} to ${endInclusive}` : dateStr,
                  totalWods: wods.length,
                  wods,
                },
                null,
                2
              ),
            },
          ],
        };
      }
    );
  }
}

// ── Worker entry point ────────────────────────────────────────────────────────

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);

    // Health check
    if (url.pathname === "/" || url.pathname === "") {
      return new Response("Octiv MCP Worker is running.", { status: 200 });
    }

    // All MCP traffic lives under /mcp — gate with bearer token
    if (url.pathname.startsWith("/mcp")) {
      const auth = request.headers.get("Authorization");
      if (auth !== `Bearer ${env.MCP_SECRET}`) {
        return new Response("Unauthorized", { status: 401 });
      }
      return OctivMCP.mount("/mcp").fetch(request, env, ctx);
    }

    return new Response("Not found", { status: 404 });
  },
};
