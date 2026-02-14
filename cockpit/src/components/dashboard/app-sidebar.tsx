"use client"

import * as React from "react"
import {
  IconBrain,
  IconChartBar,
  IconDashboard,
  IconDatabase,
  IconFileDescription,
  IconHelp,
  IconNetwork,
  IconReport,
  IconSearch,
  IconSettings,
  IconTimeline,
  IconUsers,
} from "@tabler/icons-react"

import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@/components/ui/sidebar"
import { NavDocuments } from "@/components/dashboard/nav-documents"
import { NavMain } from "@/components/dashboard/nav-main"
import { NavSecondary } from "@/components/dashboard/nav-secondary"
import { NavUser } from "@/components/dashboard/nav-user"
import { getTokenUser } from "@/lib/auth"

function useUser() {
  const tokenUser = getTokenUser()
  return {
    name: tokenUser?.full_name || tokenUser?.email?.split("@")[0] || "User",
    email: tokenUser?.email || "",
    avatar: "",
  }
}

const data = {
  navMain: [
    {
      title: "Dashboard",
      url: "#",
      icon: IconDashboard,
    },
    {
      title: "Knowledge Kernel",
      url: "#",
      icon: IconBrain,
    },
    {
      title: "Analytics",
      url: "#",
      icon: IconChartBar,
    },
    {
      title: "ACP Strategies",
      url: "#",
      icon: IconTimeline,
    },
    {
      title: "Tenants",
      url: "#",
      icon: IconUsers,
    },
  ],
  navSecondary: [
    {
      title: "Settings",
      url: "#",
      icon: IconSettings,
    },
    {
      title: "Get Help",
      url: "#",
      icon: IconHelp,
    },
    {
      title: "Search",
      url: "#",
      icon: IconSearch,
    },
  ],
  documents: [
    {
      name: "Knowledge Graph",
      url: "#",
      icon: IconNetwork,
    },
    {
      name: "Provider Status",
      url: "#",
      icon: IconDatabase,
    },
    {
      name: "Audit Logs",
      url: "/logs",
      icon: IconReport,
    },
    {
      name: "API Docs",
      url: "#",
      icon: IconFileDescription,
    },
  ],
}

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const user = useUser()

  return (
    <Sidebar collapsible="offcanvas" {...props}>
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              className="data-[slot=sidebar-menu-button]:!p-1.5"
            >
              <a href="#">
                <IconBrain className="!size-5" />
                <span className="text-base font-semibold">CogMem KOS</span>
              </a>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>
      <SidebarContent>
        <NavMain items={data.navMain} />
        <NavDocuments items={data.documents} />
        <NavSecondary items={data.navSecondary} className="mt-auto" />
      </SidebarContent>
      <SidebarFooter>
        <NavUser user={user} />
      </SidebarFooter>
    </Sidebar>
  )
}
