import { useEffect } from "react";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import DashboardTab from "@/components/tabs/DashboardTab";
import ServicesTab from "@/components/tabs/ServicesTab";
import AnalyticsTab from "@/components/tabs/AnalyticsTab";
import PriceCheckTab from "@/components/tabs/PriceCheckTab";
import StashViewerTab from "@/components/tabs/StashViewerTab";
import EconomyTab from "@/components/tabs/EconomyTab";
import MessagesTab from "@/components/tabs/MessagesTab";
import FlipFinderTab from "@/components/tabs/FlipFinderTab";
import DebugTrafficTab from "@/components/tabs/DebugTrafficTab";
import { LayoutDashboard, Server, BarChart3, Search, Grid3X3, MessageSquare, TrendingUp, Coins, Activity } from "lucide-react";
import UserMenu from "@/components/UserMenu";
import ApiErrorPanel from "@/components/ApiErrorPanel";
import { useAuth, type UserRole } from "@/services/auth";
import { useLeague } from "@/services/league";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

type TabDef = {
  id: string;
  label: string;
  icon: React.ReactNode;
  content: React.ReactNode;
  roles: UserRole[];
};

const makeTabs = (subtab?: string, onSubtabChange?: (s: string) => void): TabDef[] => [
  {
    id: "dashboard",
    label: "Dashboard",
    icon: <LayoutDashboard className="h-3.5 w-3.5" />,
    content: <DashboardTab />,
    roles: ["admin"],
  },
  {
    id: "opportunities",
    label: "Opportunities",
    icon: <TrendingUp className="h-3.5 w-3.5" />,
    content: <FlipFinderTab />,
    roles: ["member", "admin"],
  },
  {
    id: "services",
    label: "Services",
    icon: <Server className="h-3.5 w-3.5" />,
    content: <ServicesTab />,
    roles: ["admin"],
  },
  {
    id: "analytics",
    label: "Analytics",
    icon: <BarChart3 className="h-3.5 w-3.5" />,
    content: <AnalyticsTab subtab={subtab} onSubtabChange={onSubtabChange} />,
    roles: ["member", "admin"],
  },
  {
    id: "pricecheck",
    label: "ML Price",
    icon: <Search className="h-3.5 w-3.5" />,
    content: <PriceCheckTab />,
    roles: ["public", "member", "admin"],
  },
  {
    id: "stash",
    label: "Stash Viewer",
    icon: <Grid3X3 className="h-3.5 w-3.5" />,
    content: <StashViewerTab />,
    roles: ["member", "admin"],
  },
  {
    id: "economy",
    label: "Economy",
    icon: <Coins className="h-3.5 w-3.5" />,
    content: <EconomyTab />,
    roles: ["member", "admin"],
  },
  {
    id: "messages",
    label: "Messages",
    icon: <MessageSquare className="h-3.5 w-3.5" />,
    content: <MessagesTab />,
    roles: ["admin"],
  },
  {
    id: "traffic",
    label: "API Traffic",
    icon: <Activity className="h-3.5 w-3.5" />,
    content: <DebugTrafficTab />,
    roles: ["admin"],
  },
];

const DEFAULT_TAB: Record<UserRole, string> = {
  public: "pricecheck",
  member: "opportunities",
  admin: "dashboard",
};

function isEditableTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) {
    return false;
  }

  return target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable;
}

const Index = () => {
  const { userRole } = useAuth();
  const { league, setLeague, knownLeagues } = useLeague();
  const { tab, subtab } = useParams<{ tab?: string; subtab?: string }>();
  const navigate = useNavigate();

  const handleSubtabChange = (s: string) => {
    navigate(`/${tab || "analytics"}/${s}`, { replace: true });
  };

  const tabs = makeTabs(subtab, handleSubtabChange);
  const visibleTabs = tabs.filter((t) => t.roles.includes(userRole));
  const defaultTab = DEFAULT_TAB[userRole] || "pricecheck";

  // Resolve active tab: use URL param if valid, otherwise default
  const activeTab = tab && visibleTabs.some((t) => t.id === tab) ? tab : defaultTab;
  const visibleTabIds = visibleTabs.map((t) => t.id);

  const handleTabChange = (value: string) => {
    navigate(`/${value}`, { replace: false });
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (!(event.metaKey || event.ctrlKey)) {
        return;
      }
      if (isEditableTarget(event.target)) {
        return;
      }

      const currentIndex = visibleTabIds.indexOf(activeTab);
      if (currentIndex < 0 || visibleTabIds.length === 0) {
        return;
      }

      let nextIndex = -1;
      if (event.key === 'ArrowRight') {
        nextIndex = (currentIndex + 1) % visibleTabIds.length;
      } else if (event.key === 'ArrowLeft') {
        nextIndex = (currentIndex - 1 + visibleTabIds.length) % visibleTabIds.length;
      } else if (event.key === 'Home') {
        nextIndex = 0;
      } else if (event.key === 'End') {
        nextIndex = visibleTabIds.length - 1;
      }

      if (nextIndex < 0) {
        return;
      }

      event.preventDefault();
      handleTabChange(visibleTabIds[nextIndex]);
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activeTab, visibleTabIds]);

  return (
    <div className="min-h-screen bg-background vignette">
      {/* Header */}
      <header className="border-b border-border bg-card/50 backdrop-blur sticky top-0 z-50 header-glow">
        <div className="container flex items-center justify-between h-12 px-4">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="PoE Dashboard" className="h-7 w-7" />
            <h1 className="text-lg font-display tracking-wide gold-shimmer-text">PoE Dashboard</h1>
          </div>
          <div className="flex items-center gap-3">
            <Select value={league} onValueChange={setLeague}>
              <SelectTrigger className="h-8 w-[140px] text-xs border-border bg-card">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {knownLeagues.map((l) => (
                  <SelectItem key={l} value={l} className="text-xs">{l}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <ApiErrorPanel />
            <UserMenu />
          </div>
        </div>
      </header>

      {/* Main content */}
      <main className="container px-4 py-4">
        <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-4" data-testid="panel-shell-root">
          <TabsList className="w-full justify-start h-auto flex-wrap gap-1 bg-card border border-border p-1">
            {visibleTabs.map((t) => (
              <TabsTrigger
                key={t.id}
                data-testid={`tab-${t.id}`}
                value={t.id}
                className="tab-game gap-1.5 text-xs data-[state=active]:bg-primary data-[state=active]:text-primary-foreground"
              >
                {t.icon} {t.label}
              </TabsTrigger>
            ))}
          </TabsList>

          {visibleTabs.map((t) => (
            <TabsContent key={t.id} data-testid={`panel-${t.id}`} value={t.id}>
              {t.content}
            </TabsContent>
          ))}
        </Tabs>
      </main>
    </div>
  );
};

export default Index;
