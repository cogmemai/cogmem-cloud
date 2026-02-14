"use client"

import * as React from "react"
import { Area, AreaChart, CartesianGrid, XAxis } from "recharts"

import { useIsMobile } from "@/hooks/use-mobile"
import {
  Card,
  CardAction,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  ChartContainer,
  ChartTooltip,
  ChartTooltipContent,
  type ChartConfig,
} from "@/components/ui/chart"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"
import {
  ToggleGroup,
  ToggleGroupItem,
} from "@/components/ui/toggle-group"

export const description = "An interactive area chart"

const chartData = [
  { date: "2026-01-01", ingestions: 42, queries: 150 },
  { date: "2026-01-02", ingestions: 57, queries: 180 },
  { date: "2026-01-03", ingestions: 37, queries: 120 },
  { date: "2026-01-04", ingestions: 82, queries: 260 },
  { date: "2026-01-05", ingestions: 73, queries: 290 },
  { date: "2026-01-06", ingestions: 61, queries: 340 },
  { date: "2026-01-07", ingestions: 45, queries: 180 },
  { date: "2026-01-08", ingestions: 109, queries: 320 },
  { date: "2026-01-09", ingestions: 29, queries: 110 },
  { date: "2026-01-10", ingestions: 61, queries: 190 },
  { date: "2026-01-11", ingestions: 87, queries: 350 },
  { date: "2026-01-12", ingestions: 52, queries: 210 },
  { date: "2026-01-13", ingestions: 92, queries: 380 },
  { date: "2026-01-14", ingestions: 37, queries: 220 },
  { date: "2026-01-15", ingestions: 30, queries: 170 },
  { date: "2026-01-16", ingestions: 38, queries: 190 },
  { date: "2026-01-17", ingestions: 146, queries: 360 },
  { date: "2026-01-18", ingestions: 64, queries: 410 },
  { date: "2026-01-19", ingestions: 43, queries: 180 },
  { date: "2026-01-20", ingestions: 29, queries: 150 },
  { date: "2026-01-21", ingestions: 37, queries: 200 },
  { date: "2026-01-22", ingestions: 54, queries: 170 },
  { date: "2026-01-23", ingestions: 38, queries: 230 },
  { date: "2026-01-24", ingestions: 87, queries: 290 },
  { date: "2026-01-25", ingestions: 55, queries: 250 },
  { date: "2026-01-26", ingestions: 25, queries: 130 },
  { date: "2026-01-27", ingestions: 83, queries: 420 },
  { date: "2026-01-28", ingestions: 32, queries: 180 },
  { date: "2026-01-29", ingestions: 75, queries: 240 },
  { date: "2026-01-30", ingestions: 104, queries: 380 },
  { date: "2026-01-31", ingestions: 45, queries: 220 },
  { date: "2026-02-01", ingestions: 93, queries: 310 },
  { date: "2026-02-02", ingestions: 47, queries: 190 },
  { date: "2026-02-03", ingestions: 85, queries: 420 },
  { date: "2026-02-04", ingestions: 121, queries: 390 },
  { date: "2026-02-05", ingestions: 98, queries: 520 },
  { date: "2026-02-06", ingestions: 88, queries: 300 },
  { date: "2026-02-07", ingestions: 49, queries: 210 },
  { date: "2026-02-08", ingestions: 67, queries: 180 },
  { date: "2026-02-09", ingestions: 93, queries: 330 },
  { date: "2026-02-10", ingestions: 85, queries: 270 },
  { date: "2026-02-11", ingestions: 47, queries: 240 },
  { date: "2026-02-12", ingestions: 47, queries: 160 },
  { date: "2026-02-13", ingestions: 108, queries: 490 },
]

const chartConfig = {
  activity: {
    label: "Activity",
  },
  ingestions: {
    label: "Ingestions",
    color: "var(--primary)",
  },
  queries: {
    label: "Queries",
    color: "var(--primary)",
  },
} satisfies ChartConfig

export function ChartAreaInteractive() {
  const isMobile = useIsMobile()
  const [timeRange, setTimeRange] = React.useState("90d")

  React.useEffect(() => {
    if (isMobile) {
      setTimeRange("7d")
    }
  }, [isMobile])

  const filteredData = chartData.filter((item) => {
    const date = new Date(item.date)
    const referenceDate = new Date("2026-02-13")
    let daysToSubtract = 90
    if (timeRange === "30d") {
      daysToSubtract = 30
    } else if (timeRange === "7d") {
      daysToSubtract = 7
    }
    const startDate = new Date(referenceDate)
    startDate.setDate(startDate.getDate() - daysToSubtract)
    return date >= startDate
  })

  return (
    <Card className="@container/card">
      <CardHeader>
        <CardTitle>System Activity</CardTitle>
        <CardDescription>
          <span className="hidden @[540px]/card:block">
            Ingestions and queries over time
          </span>
          <span className="@[540px]/card:hidden">Activity overview</span>
        </CardDescription>
        <CardAction>
          <ToggleGroup
            type="single"
            value={timeRange}
            onValueChange={setTimeRange}
            variant="outline"
            className="hidden *:data-[slot=toggle-group-item]:!px-4 @[767px]/card:flex"
          >
            <ToggleGroupItem value="90d">Last 3 months</ToggleGroupItem>
            <ToggleGroupItem value="30d">Last 30 days</ToggleGroupItem>
            <ToggleGroupItem value="7d">Last 7 days</ToggleGroupItem>
          </ToggleGroup>
          <Select value={timeRange} onValueChange={setTimeRange}>
            <SelectTrigger
              className="flex w-40 **:data-[slot=select-value]:block **:data-[slot=select-value]:truncate @[767px]/card:hidden"
              size="sm"
              aria-label="Select a value"
            >
              <SelectValue placeholder="Last 3 months" />
            </SelectTrigger>
            <SelectContent className="rounded-xl">
              <SelectItem value="90d" className="rounded-lg">
                Last 3 months
              </SelectItem>
              <SelectItem value="30d" className="rounded-lg">
                Last 30 days
              </SelectItem>
              <SelectItem value="7d" className="rounded-lg">
                Last 7 days
              </SelectItem>
            </SelectContent>
          </Select>
        </CardAction>
      </CardHeader>
      <CardContent className="px-2 pt-4 sm:px-6 sm:pt-6">
        <ChartContainer
          config={chartConfig}
          className="aspect-auto h-[250px] w-full"
        >
          <AreaChart data={filteredData}>
            <defs>
              <linearGradient id="fillIngestions" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-ingestions)"
                  stopOpacity={1.0}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-ingestions)"
                  stopOpacity={0.1}
                />
              </linearGradient>
              <linearGradient id="fillQueries" x1="0" y1="0" x2="0" y2="1">
                <stop
                  offset="5%"
                  stopColor="var(--color-queries)"
                  stopOpacity={0.8}
                />
                <stop
                  offset="95%"
                  stopColor="var(--color-queries)"
                  stopOpacity={0.1}
                />
              </linearGradient>
            </defs>
            <CartesianGrid vertical={false} />
            <XAxis
              dataKey="date"
              tickLine={false}
              axisLine={false}
              tickMargin={8}
              minTickGap={32}
              tickFormatter={(value) => {
                const date = new Date(value)
                return date.toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                })
              }}
            />
            <ChartTooltip
              cursor={false}
              defaultIndex={isMobile ? -1 : 10}
              content={
                <ChartTooltipContent
                  labelFormatter={(value) => {
                    return new Date(value).toLocaleDateString("en-US", {
                      month: "short",
                      day: "numeric",
                    })
                  }}
                  indicator="dot"
                />
              }
            />
            <Area
              dataKey="queries"
              type="natural"
              fill="url(#fillQueries)"
              stroke="var(--color-queries)"
              stackId="a"
            />
            <Area
              dataKey="ingestions"
              type="natural"
              fill="url(#fillIngestions)"
              stroke="var(--color-ingestions)"
              stackId="a"
            />
          </AreaChart>
        </ChartContainer>
      </CardContent>
    </Card>
  )
}
