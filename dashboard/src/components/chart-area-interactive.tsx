"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

import { useIsMobile } from "@/hooks/use-mobile"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { ChartContainer, ChartTooltip, ChartTooltipContent, type ChartConfig } from "@/components/ui/chart"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"

export type Point = { date: string; applied: number; shortlisted: number }

const chartConfig = {
  applied: { label: "Applied", color: "var(--primary)" },
  shortlisted: { label: "Shortlisted", color: "var(--primary)" },
} satisfies ChartConfig

const RANGES: Record<string, { label: string; days: number }> = {
  "90d": { label: "Last 3 months", days: 90 },
  "30d": { label: "Last 30 days", days: 30 },
  "7d": { label: "Last 7 days", days: 7 },
}

export function ChartAreaInteractive({ data }: { data: Point[] }) {
  const isMobile = useIsMobile()
  // Phones default to 7 days; once the user picks a range, theirs wins.
  const [picked, setRange] = React.useState<string | null>(null)
  const range = picked ?? (isMobile ? "7d" : "30d")

  const filtered = data.slice(-RANGES[range].days)

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>Applications over time</CardTitle>
        <CardDescription>Submitted applications vs. jobs your agents shortlisted</CardDescription>
        <CardAction>
          <ToggleGroup
            multiple={false}
            value={[range]}
            onValueChange={(v) => setRange(v[0] ?? "30d")}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:px-4! @[767px]/card:flex"
          >
            {Object.entries(RANGES).map(([k, r]) => (
              <ToggleGroupItem key={k} value={k}>
                {r.label}
              </ToggleGroupItem>
            ))}
          </ToggleGroup>
          <Select value={range} onValueChange={(v) => v !== null && setRange(v)}>
            <SelectTrigger className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden" size="sm" aria-label="Select range">
              <SelectValue placeholder="Last 30 days" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              {Object.entries(RANGES).map(([k, r]) => (
                <SelectItem key={k} value={k} className="rounded-lg">
                  {r.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer config={chartConfig} className="aspect-auto h-[250px] w-full">
          <AreaChart data={filtered}>
            <defs>
              <linearGradient id="fillApplied" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-applied)" stopOpacity={1.0} />
                <stop offset="95%" stopColor="var(--color-applied)" stopOpacity={0.1} />
              </linearGradient>
              <linearGradient id="fillShortlisted" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="var(--color-shortlisted)" stopOpacity={0.8} />
                <stop offset="95%" stopColor="var(--color-shortlisted)" stopOpacity={0.1} />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={(v) => new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
            />
            <ChartTooltip
              cursor={false}
              content={<ChartTooltipContent indicator="dot" labelFormatter={(v) => new Date(v).toLocaleDateString("en-US", { month: "short", day: "numeric" })} />}
            />
            <Area dataKey="shortlisted" type="monotone" fill="url(#fillShortlisted)" stroke="var(--color-shortlisted)" stackId="a" />
            <Area dataKey="applied" type="monotone" fill="url(#fillApplied)" stroke="var(--color-applied)" stackId="a" />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
