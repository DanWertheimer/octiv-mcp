// ── Formatting helpers (TypeScript port of server.py formatting functions) ────

/** Convert 'HH:MM:SS' to 'H:MM AM/PM'. */
export function formatTime(t: string): string {
  try {
    const [h, m] = t.split(":").map(Number);
    const period = h >= 12 ? "PM" : "AM";
    const hour = h % 12 || 12;
    return `${hour}:${m.toString().padStart(2, "0")} ${period}`;
  } catch {
    return t;
  }
}

/** Return Monday and Sunday of the current (or offset) week as YYYY-MM-DD. */
export function weekBounds(offsetWeeks: number = 0): [string, string] {
  const today = new Date();
  // JS getDay(): 0=Sun, 1=Mon … 6=Sat → convert to Mon-anchored offset
  const dayOfWeek = today.getDay();
  const daysFromMonday = dayOfWeek === 0 ? 6 : dayOfWeek - 1;

  const monday = new Date(today);
  monday.setDate(today.getDate() - daysFromMonday + offsetWeeks * 7);
  const sunday = new Date(monday);
  sunday.setDate(monday.getDate() + 6);

  return [toDateString(monday), toDateString(sunday)];
}

function toDateString(d: Date): string {
  return d.toISOString().split("T")[0];
}

export interface MyBooking {
  status: string;
  checkedIn: boolean;
  checkedOut: boolean;
}

export interface ClassSummary {
  classDateId: unknown;
  date: unknown;
  name: unknown;
  startTime: string;
  endTime: string;
  instructor: string;
  capacity: unknown;
  booked: number;
  available: number;
  waitingList: unknown;
  description: unknown;
  myBooking?: MyBooking;
}

type AnyObject = Record<string, unknown>;

/** Convert raw /api/class-dates response into a clean list of class summaries. */
export function formatSchedule(data: AnyObject, myUserId?: number): ClassSummary[] {
  const classes = (data["data"] as AnyObject[]) ?? [];

  return classes.map((cls) => {
    const bookings = (cls["bookings"] as AnyObject[]) ?? [];
    const activeBookings = bookings.filter(
      (b) => (b["status"] as AnyObject | undefined)?.["name"] === "BOOKED"
    );
    const waitList = (cls["waitingListCount"] as number) ?? 0;

    const instructor = (cls["instructor"] as AnyObject | null) ?? {};
    const instructorName =
      `${instructor["name"] ?? ""} ${instructor["surname"] ?? ""}`.trim() || "TBA";

    const capacity = (cls["limit"] as number) ?? 0;
    const summary: ClassSummary = {
      classDateId: cls["id"],
      date: cls["date"],
      name: cls["name"],
      startTime: formatTime((cls["startTime"] as string) ?? ""),
      endTime: formatTime((cls["endTime"] as string) ?? ""),
      instructor: instructorName,
      capacity,
      booked: activeBookings.length,
      available: Math.max(0, capacity - activeBookings.length),
      waitingList: waitList,
      description: (cls["description"] as string) ?? "",
    };

    if (myUserId !== undefined) {
      const myBooking = bookings.find((b) => b["userId"] === myUserId);
      if (myBooking) {
        const status =
          ((myBooking["status"] as AnyObject | undefined)?.["name"] as string) ?? "UNKNOWN";
        summary.myBooking = {
          status,
          checkedIn: myBooking["checkedInAt"] != null,
          checkedOut: myBooking["checkedOutAt"] != null,
        };
      }
    }

    return summary;
  });
}

export interface Exercise {
  order: number;
  name: string;
  description: string;
  measuringUnit: string;
}

export interface WodSummary {
  id: unknown;
  date: string;
  warmUp: string;
  coolDown: string;
  coachNotes: string;
  memberNotes: string;
  exercises: Exercise[];
}

/** Convert raw /api/wods response into a clean list of WOD summaries. */
export function formatWod(data: AnyObject): WodSummary[] {
  const wods = (data["data"] as AnyObject[]) ?? [];

  return wods.map((wod) => {
    const wodExercises = ((wod["wodExercises"] as AnyObject[]) ?? [])
      .filter((we) => we["isActive"] !== false)
      .sort((a, b) => ((a["order"] as number) ?? 0) - ((b["order"] as number) ?? 0));

    const exercises: Exercise[] = wodExercises.map((we) => {
      const ex = (we["exercise"] as AnyObject) ?? {};
      const mu = (ex["measuringUnit"] as AnyObject) ?? {};
      return {
        order: (we["order"] as number) ?? 0,
        name: (ex["name"] as string) ?? "",
        description: ((ex["description"] as string) ?? "").trim(),
        measuringUnit: (mu["name"] as string) ?? "",
      };
    });

    return {
      id: wod["id"],
      date: (wod["date"] as string) ?? "",
      warmUp: ((wod["warmUp"] as string) ?? "").trim(),
      coolDown: ((wod["coolDown"] as string) ?? "").trim(),
      coachNotes: ((wod["coachNotes"] as string) ?? "").trim(),
      memberNotes: ((wod["memberNotes"] as string) ?? "").trim(),
      exercises,
    };
  });
}
