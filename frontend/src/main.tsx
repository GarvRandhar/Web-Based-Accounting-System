import React from "react";
import ReactDOM from "react-dom/client";
import { AppSidebar } from "@/components/ui/app-sidebar";
import LoginCardSection from "@/components/ui/login-signup";
import "./index.css";

const rootEl = document.getElementById("react-sidebar-root");

if (rootEl) {
    // Read Flask template data from data attributes
    const companyName = rootEl.dataset.companyName || "AcctPro";
    const currentEndpoint = rootEl.dataset.currentEndpoint || "";
    const isAdmin = rootEl.dataset.isAdmin === "true";
    const userName = rootEl.dataset.userName || "User";

    // Read navigation URLs from data attributes
    const navUrls: Record<string, string> = {};
    const urlKeys = [
        "dashboard",
        "journals",
        "accounts",
        "invoices",
        "ar_aging",
        "bills",
        "ap_aging",
        "customers",
        "vendors",
        "reports",
        "reconciliation",
        "audit_log",
        "settings",
        "products",
        "warehouses",
        "stock_entry",
        "stock_ledger",
        "tax_groups",
        "cost_centers",
        "cost_center_report",
        "currencies",
        "employees",
        "salary_components",
        "salary_structures",
        "payroll_process",
        "assets",
        "new_asset",
        "logout",
    ];

    for (const key of urlKeys) {
        const attrName = `url${key.charAt(0).toUpperCase()}${key.slice(1).replace(/_([a-z])/g, (_, c) => c.toUpperCase())}`;
        const value = rootEl.dataset[attrName];
        if (value) {
            navUrls[key] = value;
        }
    }

    ReactDOM.createRoot(rootEl).render(
        <React.StrictMode>
            <AppSidebar
                companyName={companyName}
                currentEndpoint={currentEndpoint}
                isAdmin={isAdmin}
                userName={userName}
                navUrls={navUrls}
            />
        </React.StrictMode>
    );
}

const loginRootEl = document.getElementById("react-login-root");
if (loginRootEl) {
    const mode = (loginRootEl.dataset.mode || "login") as "login" | "register";
    const csrfToken = loginRootEl.dataset.csrfToken || "";
    const error = loginRootEl.dataset.error || "";
    const loginUrl = loginRootEl.dataset.loginUrl || "";
    const registerUrl = loginRootEl.dataset.registerUrl || "";

    ReactDOM.createRoot(loginRootEl).render(
        <React.StrictMode>
            <LoginCardSection
                mode={mode}
                csrfToken={csrfToken}
                error={error}
                loginUrl={loginUrl}
                registerUrl={registerUrl}
            />
        </React.StrictMode>
    );
}
