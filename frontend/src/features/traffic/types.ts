/** Short names for the traffic API types (generated into schema.d.ts by `make api-client`). */
import type { components } from "@/lib/api/schema"

type Schemas = components["schemas"]

export type TraceSummary = Schemas["TraceSummary"]
export type TraceOut = Schemas["TraceOut"]
export type ImportReport = Schemas["ImportReport"]
export type FormatOut = Schemas["FormatOut"]
export type MakeCasesOut = Schemas["MakeCasesOut"]
export type TrafficStats = Schemas["TrafficStats"]
export type DailyScore = Schemas["DailyScore"]
export type ConfigOut = Schemas["ConfigOut"]
export type ConfigUpdate = Schemas["ConfigUpdate"]
export type TokenOut = Schemas["TokenOut"]
export type TokenCreated = Schemas["TokenCreated"]
export type ChannelOut = Schemas["ChannelOut"]
export type ChannelCreate = Schemas["ChannelCreate"]
export type RuleOut = Schemas["RuleOut"]
export type RuleCreate = Schemas["RuleCreate"]
export type AlertOut = Schemas["AlertOut"]

export type TraceFilters = {
  failed: boolean
  low_rated: boolean
  long: boolean
  new_topic: boolean
  unused: boolean
  q: string
}
