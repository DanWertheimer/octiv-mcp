// ── Octiv API client (TypeScript port of the Python OctivClient) ──────────────

const API_BASE = "https://api.octivfitness.com";

export interface Env {
  MCP_SECRET: string;
  OCTIV_USERNAME: string;
  OCTIV_PASSWORD: string;
  OCTIV_TENANT_ID?: string;
  OCTIV_LOCATION_ID?: string;
  OCTIV_PROGRAMME_IDS?: string;
  // Durable Object namespace — resolved by the agents SDK under the hood
  OctivMCP: DurableObjectNamespace;
}

type AnyObject = Record<string, unknown>;

export class OctivClient {
  private env: Env;
  // In-memory cache (lives for the lifetime of the Durable Object instance)
  private _token: string | null = null;
  private _tokenExpiresAt: number = 0; // Unix seconds
  private _userInfo: AnyObject | null = null;

  constructor(env: Env) {
    if (!env.OCTIV_USERNAME || !env.OCTIV_PASSWORD) {
      throw new Error(
        "OCTIV_USERNAME and OCTIV_PASSWORD environment variables must be set."
      );
    }
    this.env = env;
  }

  // ── Token management ────────────────────────────────────────────────────────

  private async getToken(): Promise<string> {
    // Reuse cached token if still valid (1-hour buffer before expiry)
    if (this._token && this._tokenExpiresAt > Date.now() / 1000 + 3600) {
      return this._token;
    }

    const resp = await fetch(`${API_BASE}/api/login`, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
        "x-camelcase": "true",
      },
      body: JSON.stringify({
        username: this.env.OCTIV_USERNAME,
        password: this.env.OCTIV_PASSWORD,
      }),
    });

    if (!resp.ok) {
      throw new Error(`Login failed: ${resp.status} ${await resp.text()}`);
    }

    const data = (await resp.json()) as AnyObject;
    this._token = data["accessToken"] as string;
    this._tokenExpiresAt =
      Date.now() / 1000 + ((data["expiresIn"] as number) ?? 31536000);
    return this._token;
  }

  private invalidateToken(): void {
    this._token = null;
    this._tokenExpiresAt = 0;
  }

  private async authHeaders(): Promise<Record<string, string>> {
    const token = await this.getToken();
    return {
      Authorization: `Bearer ${token}`,
      Accept: "application/json",
      "Content-Type": "application/json",
      "x-camelcase": "true",
    };
  }

  // ── User / gym info ─────────────────────────────────────────────────────────

  async getMe(): Promise<AnyObject> {
    if (this._userInfo) return this._userInfo;

    const headers = await this.authHeaders();
    const resp = await fetch(`${API_BASE}/api/users/me`, { headers });
    if (!resp.ok) {
      throw new Error(`Failed to get user profile: ${resp.status} ${await resp.text()}`);
    }
    this._userInfo = (await resp.json()) as AnyObject;
    return this._userInfo;
  }

  extractGymIds(me: AnyObject): [string, string] {
    let tenantId = this.env.OCTIV_TENANT_ID;
    let locationId = this.env.OCTIV_LOCATION_ID;

    if (!tenantId || !locationId) {
      // Auto-detect from the userTenants array in the /me response
      const userTenants = (me["userTenants"] as AnyObject[]) ?? [];
      const userTenant =
        userTenants.find((t) => t["defaultLocationId"]) ?? userTenants[0] ?? {};
      tenantId = tenantId ?? String(userTenant["tenantId"] ?? "");
      locationId = locationId ?? String(userTenant["defaultLocationId"] ?? "");
    }

    if (!tenantId) {
      throw new Error(
        "Could not determine your gym's tenant ID. " +
          "Please set the OCTIV_TENANT_ID environment variable."
      );
    }
    if (!locationId) {
      throw new Error(
        "Could not determine your gym's location ID. " +
          "Please set the OCTIV_LOCATION_ID environment variable."
      );
    }
    return [tenantId, locationId];
  }

  // ── API calls ───────────────────────────────────────────────────────────────

  async getClassDates(startDate: string, endDate: string): Promise<AnyObject> {
    const headers = await this.authHeaders();
    const me = await this.getMe();
    const [tenantId, locationId] = this.extractGymIds(me);

    const params = new URLSearchParams({
      include: "classBookings.user",
      "filter[tenantId]": tenantId,
      "filter[locationId]": locationId,
      "filter[between]": `${startDate},${endDate}`,
      "filter[isSession]": "0",
      internalAppend: "withoutLocations",
      perPage: "-1",
    });

    const resp = await fetch(`${API_BASE}/api/class-dates?${params}`, { headers });
    if (resp.status === 401) {
      this.invalidateToken();
      throw new Error("Authentication expired. Please retry.");
    }
    if (!resp.ok) {
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }
    return (await resp.json()) as AnyObject;
  }

  async getProgrammes(): Promise<AnyObject> {
    const headers = await this.authHeaders();
    const me = await this.getMe();
    const [tenantId] = this.extractGymIds(me);

    const params = new URLSearchParams({
      "filter[tenantId]": tenantId,
      perPage: "-1",
    });

    const resp = await fetch(`${API_BASE}/api/programmes?${params}`, { headers });
    if (resp.status === 401) {
      this.invalidateToken();
      throw new Error("Authentication expired. Please retry.");
    }
    if (!resp.ok) {
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }
    return (await resp.json()) as AnyObject;
  }

  async getWods(
    startDate: string,
    endDate: string,
    programmeIds?: string
  ): Promise<AnyObject> {
    const headers = await this.authHeaders();
    const me = await this.getMe();
    const [tenantId] = this.extractGymIds(me);

    const pids = programmeIds ?? this.env.OCTIV_PROGRAMME_IDS;
    const params = new URLSearchParams({
      "filter[tenantId]": tenantId,
      "filter[startsAfter]": startDate,
      "filter[endsBefore]": endDate,
      "filter[useWorkoutThreshold]": "1",
    });
    if (pids) {
      params.set("filter[programmeIds]", pids);
    }

    const resp = await fetch(`${API_BASE}/api/wods?${params}`, { headers });
    if (resp.status === 401) {
      this.invalidateToken();
      throw new Error("Authentication expired. Please retry.");
    }
    if (!resp.ok) {
      throw new Error(`API error ${resp.status}: ${await resp.text()}`);
    }
    return (await resp.json()) as AnyObject;
  }
}
