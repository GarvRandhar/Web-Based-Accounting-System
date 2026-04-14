import { useState } from "react";
import { Sidebar, SidebarBody, SidebarLink } from "@/components/ui/sidebar";
import {
    LayoutDashboard,
    BookOpen,
    ListTree,
    FileText,
    Receipt,
    Users,
    Building2,
    BarChart3,
    Scale,
    ShieldCheck,
    Settings,
    LogOut,
    Package,
    Warehouse,
    Calculator,
    Target,
    Coins,
    UserCheck,
    Landmark,
} from "lucide-react";
import { motion } from "framer-motion";
import { cn } from "@/lib/utils";

interface AppSidebarProps {
    companyName: string;
    currentEndpoint: string;
    isAdmin: boolean;
    userName: string;
    navUrls: Record<string, string>;
}

export function AppSidebar({
    companyName,
    currentEndpoint,
    isAdmin,
    userName,
    navUrls,
}: AppSidebarProps) {
    const links = [
        {
            label: "Dashboard",
            href: navUrls.dashboard || "/",
            icon: (
                <LayoutDashboard className="text-neutral-300 h-5 w-5 flex-shrink-0" />
            ),
            matchKey: "main.dashboard",
        },
        {
            label: "Journal Entries",
            href: navUrls.journals || "/accounting/journals",
            icon: <BookOpen className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "accounting",
        },
        {
            label: "Chart of Accounts",
            href: navUrls.accounts || "/accounting/accounts",
            icon: <ListTree className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "accounting.list_accounts",
        },
        {
            label: "Invoices",
            href: navUrls.invoices || "/ar/invoices",
            icon: <FileText className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ar",
        },
        {
            label: "AR Aging Report",
            href: navUrls.ar_aging || "/ar/aging",
            icon: <BarChart3 className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ar.aging_report",
        },
        {
            label: "Bills",
            href: navUrls.bills || "/ap/bills",
            icon: <Receipt className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ap.bills",
        },
        {
            label: "AP Aging Report",
            href: navUrls.ap_aging || "/ap/aging",
            icon: <BarChart3 className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ap.aging_report",
        },
        {
            label: "Customers",
            href: navUrls.customers || "/ar/customers",
            icon: <Users className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ar.customers",
        },
        {
            label: "Vendors",
            href: navUrls.vendors || "/ap/vendors",
            icon: <Building2 className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "ap.vendors",
        },
        {
            label: "Products",
            href: navUrls.products || "/inventory/products",
            icon: <Package className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "inventory.products",
        },
        {
            label: "Warehouses",
            href: navUrls.warehouses || "/inventory/warehouses",
            icon: <Warehouse className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "inventory.warehouses",
        },
        {
            label: "Stock Ledger",
            href: navUrls.stock_ledger || "/inventory/stock-ledger",
            icon: <Package className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "inventory.stock_ledger",
        },
        {
            label: "Tax Groups",
            href: navUrls.tax_groups || "/taxation/",
            icon: <Calculator className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "taxation",
        },
        {
            label: "Cost Centers",
            href: navUrls.cost_centers || "/cost-centers/",
            icon: <Target className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "cost_centers",
        },
        {
            label: "Currencies",
            href: navUrls.currencies || "/currencies/",
            icon: <Coins className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "currency",
        },
        {
            label: "Employees",
            href: navUrls.employees || "/payroll/employees",
            icon: <UserCheck className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "payroll.employees",
        },
        {
            label: "Payroll",
            href: navUrls.payroll_process || "/payroll/process",
            icon: <UserCheck className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "payroll.process",
        },
        {
            label: "Fixed Assets",
            href: navUrls.assets || "/assets/",
            icon: <Landmark className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "assets",
        },
        {
            label: "Reports",
            href: navUrls.reports || "/reports",
            icon: <BarChart3 className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "reports",
        },
        {
            label: "Reconciliation",
            href: navUrls.reconciliation || "/reconciliation",
            icon: <Scale className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "reconciliation",
        },
    ];

    const adminLinks = [
        {
            label: "Audit Log",
            href: navUrls.audit_log || "/admin/audit-log",
            icon: (
                <ShieldCheck className="text-neutral-300 h-5 w-5 flex-shrink-0" />
            ),
            matchKey: "admin",
        },
        {
            label: "Settings",
            href: navUrls.settings || "/settings",
            icon: <Settings className="text-neutral-300 h-5 w-5 flex-shrink-0" />,
            matchKey: "settings",
        },
    ];

    const allLinks = isAdmin ? [...links, ...adminLinks] : links;

    const isActive = (matchKey: string) => {
        if (matchKey === currentEndpoint) return true;
        if (
            matchKey !== "main.dashboard" &&
            !matchKey.includes(".") &&
            currentEndpoint.startsWith(matchKey + ".")
        )
            return true;
        return false;
    };

    const [open, setOpen] = useState(false);

    return (
        <div
            className={cn(
                "flex flex-col md:flex-row flex-shrink-0 h-screen"
            )}
        >
            <Sidebar open={open} setOpen={setOpen}>
                <SidebarBody className="justify-between gap-10 bg-[#1a1f36] dark:bg-neutral-900">
                    <div className="flex flex-col flex-1 overflow-y-auto overflow-x-hidden">
                        {open ? (
                            <Logo companyName={companyName} />
                        ) : (
                            <LogoIcon companyName={companyName} />
                        )}
                        <div className="mt-8 flex flex-col gap-2">
                            {allLinks.map((link, idx) => (
                                <SidebarLink
                                    key={idx}
                                    link={link}
                                    active={isActive(link.matchKey)}
                                />
                            ))}
                        </div>
                    </div>
                    <div>
                        <SidebarLink
                            link={{
                                label: userName,
                                href: navUrls.logout || "/auth/logout",
                                icon: (
                                    <LogOut className="text-neutral-300 h-5 w-5 flex-shrink-0" />
                                ),
                            }}
                        />
                    </div>
                </SidebarBody>
            </Sidebar>
        </div>
    );
}

const Logo = ({ companyName }: { companyName: string }) => {
    return (
        <a
            href="/"
            className="font-normal flex space-x-2 items-center text-sm text-white py-1 relative z-20 no-underline"
        >
            <div className="h-5 w-6 bg-white rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm flex-shrink-0" />
            <motion.span
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                className="font-semibold text-white whitespace-pre"
            >
                {companyName}
            </motion.span>
        </a>
    );
};

const LogoIcon = ({ companyName: _companyName }: { companyName: string }) => {
    return (
        <a
            href="/"
            className="font-normal flex space-x-2 items-center text-sm text-white py-1 relative z-20 no-underline"
        >
            <div className="h-5 w-6 bg-white rounded-br-lg rounded-tr-sm rounded-tl-lg rounded-bl-sm flex-shrink-0" />
        </a>
    );
};
