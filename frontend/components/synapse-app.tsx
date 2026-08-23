"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useDropzone } from "react-dropzone";
import {
  applications,
  auditEvents,
  rules,
  type Application,
  type View,
} from "@/lib/types";
import {
  Activity,
  AlertCircle,
  ArrowDown,
  ArrowUp,
  BadgeCheck,
  BarChart3,
  BookOpen,
  Check,
  ChevronDown,
  ChevronRight,
  Clock3,
  Copy,
  FileCheck2,
  FileText,
  Filter,
  FolderOpen,
  Gauge,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  ShieldCheck,
  Sun,
  UploadCloud,
  UsersRound,
  XCircle,
} from "lucide-react";

type Props = { view: View; applicationId?: string };
type DemoRole = "ADMIN" | "USER";
let sidebarCollapsed = false;
let darkTheme = false;
let activeRole: DemoRole = "ADMIN";

const nav = [
  { label: "Dashboard", href: "/", icon: LayoutDashboard },
  { label: "Applications", href: "/applications/APP-00016", icon: FolderOpen },
  { label: "Policies", href: "/policies", icon: BookOpen },
  { label: "Audit log", href: "/audit", icon: History },
  { label: "Reports", href: "/reports", icon: BarChart3 },
];
const statusMeta: Record<
  string,
  { icon: typeof Check; color: string; bg: string }
> = {
  ELIGIBLE: { icon: Check, color: "#0f766e", bg: "#e6f4f1" },
  NEEDS_REVIEW: { icon: AlertCircle, color: "#b45309", bg: "#fff4df" },
  INELIGIBLE: { icon: XCircle, color: "#b91c1c", bg: "#fdecec" },
  PROCESSING: { icon: Clock3, color: "#405466", bg: "#edf1f4" },
};

function StatusBadge({ status }: { status: string }) {
  const meta = statusMeta[status] ?? statusMeta.PROCESSING;
  const Icon = meta.icon;
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-[5px] border px-2 py-1 text-[11px] font-semibold tracking-wide"
      style={{
        color: meta.color,
        background: meta.bg,
        borderColor: `${meta.color}55`,
      }}
    >
      <Icon size={13} strokeWidth={2} />
      {status.replaceAll("_", " ")}
    </span>
  );
}
function Button({
  children,
  href,
  onClick,
  secondary = false,
}: {
  children: React.ReactNode;
  href?: string;
  onClick?: () => void;
  secondary?: boolean;
}) {
  const cn = `inline-flex h-9 items-center justify-center gap-2 rounded-[4px] border px-3 text-xs font-semibold transition-colors ${secondary ? "border-[#d8dee4] bg-white text-[#405466] hover:bg-[#f5f7fa]" : "border-[#0f766e] bg-[#0f766e] text-white hover:bg-[#0c625d]"}`;
  return href ? (
    <Link href={href} className={cn}>
      {children}
    </Link>
  ) : (
    <button onClick={onClick} className={cn}>
      {children}
    </button>
  );
}
function CopyButton({ value }: { value: string }) {
  return (
    <button
      aria-label={`Copy ${value}`}
      className="text-[#405466] hover:text-[#0f766e]"
      onClick={() => navigator.clipboard?.writeText(value)}
    >
      <Copy size={15} />
    </button>
  );
}
function FieldLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-1 text-[10px] font-bold uppercase tracking-[.12em] text-[#718294]">
      {children}
    </div>
  );
}
function Quote({ children }: { children: React.ReactNode }) {
  return (
    <blockquote className="border-l-2 border-[#405466] pl-3 font-serif text-[13px] italic leading-5 text-[#405466]">
      “{children}”
    </blockquote>
  );
}
function Quality({ quality }: { quality: string }) {
  const colors: Record<string, string> = {
    HIGH: "#0f766e",
    MEDIUM: "#405466",
    LOW: "#b45309",
    INSUFFICIENT: "#b91c1c",
  };
  return (
    <div
      className="flex items-center gap-2 text-xs font-semibold"
      style={{ color: colors[quality] }}
    >
      <span className="flex gap-1">
        {[1, 2, 3, 4].map((n) => (
          <i
            key={n}
            className="h-2 w-4 rounded-[1px]"
            style={{
              background:
                n <=
                ({ HIGH: 4, MEDIUM: 3, LOW: 2, INSUFFICIENT: 1 }[quality] ?? 1)
                  ? colors[quality]
                  : "#d8dee4",
            }}
          />
        ))}
      </span>
      {quality}
    </div>
  );
}

function Shell({
  children,
  current,
}: {
  children: React.ReactNode;
  current: string;
}) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [collapsed, setCollapsedState] = useState(sidebarCollapsed);
  const [dark, setDarkState] = useState(darkTheme);
  const [role, setRole] = useState<DemoRole>(activeRole);
  const [preferencesReady, setPreferencesReady] = useState(false);

  useEffect(() => {
    const frame = window.requestAnimationFrame(() => {
      const savedCollapsed = window.localStorage.getItem("synapse-sidebar") === "collapsed";
      sidebarCollapsed = savedCollapsed;
      setCollapsedState(savedCollapsed);
      darkTheme = window.localStorage.getItem("synapse-theme") === "dark";
      setDarkState(darkTheme);
      activeRole =
        window.localStorage.getItem("synapse-role") === "USER"
          ? "USER"
          : "ADMIN";
      setRole(activeRole);
      setPreferencesReady(true);
    });
    return () => window.cancelAnimationFrame(frame);
  }, []);

  useEffect(() => {
    if (!preferencesReady) return;
    window.localStorage.setItem("synapse-theme", dark ? "dark" : "light");
  }, [dark, preferencesReady]);

  useEffect(() => {
    if (!preferencesReady) return;
    window.localStorage.setItem("synapse-sidebar", collapsed ? "collapsed" : "expanded");
  }, [collapsed, preferencesReady]);

  const setCollapsed = (value: boolean) => {
    sidebarCollapsed = value;
    setCollapsedState(value);
  };
  const setDark = (value: boolean) => {
    darkTheme = value;
    setDarkState(value);
  };
  const navigation =
    role === "USER"
      ? [
          { label: "Upload", href: "/upload", icon: UploadCloud },
          {
            label: "Processing",
            href: "/applications/APP-00020",
            icon: Clock3,
          },
        ]
      : nav;

  return (
    <div data-theme={dark ? "dark" : "light"} style={{ backgroundColor: dark ? "#0e1c28" : "#f5f7fa" }} className="workspace-bg min-h-screen bg-[#f5f7fa] text-[#12304a] transition-colors duration-200">
      {open && <button className="fixed inset-0 z-10 bg-[#12304a]/35 lg:hidden" onClick={() => setOpen(false)} aria-label="Close navigation" />}
      <aside
        className={`fixed inset-y-0 left-0 z-20 ${collapsed ? "w-[76px]" : "w-[232px]"} border-r border-white/10 bg-[#12304a] px-4 py-5 text-white shadow-[4px_0_18px_rgba(18,48,74,.12)] transition-[width,transform] duration-200 lg:translate-x-0 ${open ? "translate-x-0" : "-translate-x-full"}`}
      >
        <div className={`mb-10 flex items-center gap-3 px-2 ${collapsed ? "justify-center" : ""}`}>
          <span className="grid h-8 w-8 place-items-center rounded-[4px] border border-[#69b8b0] text-[#72c9bf]">
            <ShieldCheck size={19} />
          </span>
          <div className={collapsed ? "hidden" : ""}>
            <div className="font-mono text-[17px] font-bold tracking-tight">
              SYNAPSE
            </div>
            <div className="text-[9px] uppercase tracking-[.18em] text-slate-300">
              provenance layer
            </div>
          </div>
        </div>
        <nav className="space-y-1">
          {navigation.map(({ label, href, icon: Icon }) => (
            <Link
              key={label}
              href={href}
              title={collapsed ? label : undefined}
              className={`relative flex h-10 items-center gap-3 px-3 text-sm ${current === label ? "font-semibold text-white" : "text-slate-300 hover:text-white"}`}
            >
              {current === label && (
                <span className="absolute left-0 h-5 w-0.5 bg-[#54b9ae]" />
              )}
              <Icon size={18} strokeWidth={1.75} />
              <span className={collapsed ? "hidden" : ""}>{label}</span>
            </Link>
          ))}
        </nav>
        <div className={`absolute bottom-5 ${collapsed ? "left-3 right-3" : "left-5 right-5"} border-t border-white/10 pt-4`}>
          <div className={`mb-4 flex items-center gap-2 text-xs text-[#b7c5d1] ${collapsed ? "justify-center" : ""}`}>
            <span className="h-2 w-2 rounded-full bg-[#54b9ae]" /> All systems
            <span className={collapsed ? "hidden" : ""}>operational</span>
          </div>
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#405466] text-xs font-bold">
              RK
            </span>
            <div className={collapsed ? "hidden" : ""}>
              <div className="text-xs font-semibold">
                {role === "USER" ? "Demo Applicant" : "Riya Kapoor"}
              </div>
              <div className="text-[10px] text-slate-400">
                {role === "USER" ? "Applicant" : "Auditor"}
              </div>
            </div>
            <button
              className="ml-auto text-slate-400 hover:text-white"
              onClick={() => {
                window.localStorage.removeItem("synapse-role");
                router.push("/login");
              }}
              aria-label="Sign out"
              title="Sign out"
            >
              <LogOut size={15} />
            </button>
          </div>
          <button onClick={() => setCollapsed(!collapsed)} className={`mt-4 hidden h-8 w-full items-center justify-center gap-2 rounded-[4px] border border-white/10 text-[10px] text-slate-300 transition-colors hover:border-[#69b8b0] hover:text-white lg:flex ${collapsed ? "px-0" : "px-2"}`} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
            {collapsed ? <PanelLeftOpen size={15} /> : <><PanelLeftClose size={15} /> Collapse navigation</>}
          </button>
        </div>
      </aside>
      <div className={`transition-[padding] duration-200 ${collapsed ? "lg:pl-[76px]" : "lg:pl-[232px]"}`}>
        <header className="sticky top-0 z-10 flex h-[64px] items-center justify-between border-b border-[#d8dee4] bg-[#f5f7fa]/95 px-5 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              className="lg:hidden"
              onClick={() => setOpen(!open)}
              aria-label="Open navigation"
            >
              <Menu size={20} />
            </button>
            <button className="hidden text-[#405466] lg:block" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"} title={collapsed ? "Expand sidebar" : "Collapse sidebar"}>
              {collapsed ? <PanelLeftOpen size={19} /> : <PanelLeftClose size={19} />}
            </button>
            <div>
              <div className="text-[10px] font-bold uppercase tracking-[.14em] text-[#718294]">
                Decision operations
              </div>
              <div className="text-lg font-semibold">{current}</div>
            </div>
          </div>
          <div className="flex items-center gap-4">
            <div className="hidden items-center gap-2 border-b border-[#aab8c4] px-1 py-1 sm:flex">
              <Search size={16} className="text-[#718294]" />
              <input
                className="w-44 bg-transparent text-xs outline-none placeholder:text-[#8b9aa8]"
                placeholder="Search applications"
              />
            </div>
            <button
              aria-label="Notifications"
              className="relative text-[#405466]"
            >
              <Activity size={19} />
              <i className="absolute -right-0.5 -top-0.5 h-1.5 w-1.5 rounded-full bg-[#b45309]" />
            </button>
            <button aria-label={dark ? "Switch to light theme" : "Switch to dark theme"} title={dark ? "Light theme" : "Dark theme"} onClick={() => setDark(!dark)} className="grid h-8 w-8 place-items-center rounded-[4px] border border-[#d8dee4] text-[#405466] transition-colors hover:border-[#0f766e] hover:text-[#0f766e]">
              {dark ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#dfe9e9] text-xs font-bold text-[#0f766e]">
              RK
            </span>
          </div>
        </header>
        {children}
      </div>
    </div>
  );
}

function UploadView() {
  const [uploaded, setUploaded] = useState<
    {
      id: string;
      name: string;
      size: string;
      type: string;
      hash: string;
      uploadStatus: "UPLOADED" | "QUEUED";
      processingStatus: "READY" | "PROCESSING" | "SCANNED";
    }[]
  >([]);
  const [step, setStep] = useState(0);
  const steps = [
    "Uploading",
    "Processing",
    "OCR",
    "Extracting",
    "Validating",
    "Evaluating Rules",
    "Complete",
  ];

  const onDrop = (files: File[]) => {
    const next = files.map((file, i) => ({
      id: `${file.name}-${Date.now()}-${i}`,
      name: file.name,
      size: `${(file.size / (1024 * 1024)).toFixed(2)} MB`,
      type: file.type.includes("pdf") ? "PDF" : "IMAGE",
      hash: `${Math.random().toString(16).slice(2, 8)}...`,
      uploadStatus: "UPLOADED" as const,
      processingStatus: "READY" as const,
    }));
    setUploaded((prev) => [...prev, ...next]);
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
    accept: {
      "application/pdf": [".pdf"],
      "image/jpeg": [".jpg", ".jpeg"],
      "image/png": [".png"],
    },
  });

  const runProcessing = () => {
    setUploaded((prev) =>
      prev.map((item) => ({ ...item, processingStatus: "PROCESSING" })),
    );
    setStep(1);
    let idx = 1;
    const timer = setInterval(() => {
      idx += 1;
      setStep(idx);
      if (idx >= steps.length - 1) {
        clearInterval(timer);
        setUploaded((prev) =>
          prev.map((item) => ({ ...item, processingStatus: "SCANNED" })),
        );
      }
    }, 800);
  };

  return (
    <Shell current="Upload">
      <main className="mx-auto max-w-[1200px] p-5 lg:p-8">
        <PageHead
          eyebrow="Applicant workspace"
          title="Upload documents for OCR"
          sub="Submit scheme documents for extraction and evidence-based eligibility checks."
        />

        <section className="mb-5 grid gap-4 border border-[#d8dee4] bg-white p-5 md:grid-cols-2">
          <label className="text-xs font-semibold text-[#405466]">
            Scheme
            <select className="mt-2 h-10 w-full rounded-[4px] border border-[#d8dee4] bg-white px-3 text-sm">
              <option>Education Assistance Scheme</option>
              <option>Housing Support Scheme</option>
              <option>Medical Assistance Scheme</option>
            </select>
          </label>
          <label className="text-xs font-semibold text-[#405466]">
            Applicant reference
            <input
              className="mt-2 h-10 w-full rounded-[4px] border border-[#d8dee4] px-3 text-sm"
              defaultValue="APL-****-2407"
            />
          </label>
        </section>

        <section className="mb-5 border border-[#d8dee4] bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold">Required documents</h2>
          <div className="grid gap-2 text-xs sm:grid-cols-2">
            {["Government ID", "Income Certificate", "Bank Statement", "Residence Proof"].map((doc, i) => (
              <div key={doc} className="flex items-center gap-2 text-[#405466]">
                <span
                  className={`inline-grid h-4 w-4 place-items-center rounded-[3px] border ${i < 2 ? "border-[#0f766e] bg-[#e6f4f1] text-[#0f766e]" : "border-[#d8dee4] text-[#718294]"}`}
                >
                  {i < 2 ? "✓" : "○"}
                </span>
                {doc}
              </div>
            ))}
          </div>
        </section>

        <section className="mb-5 border border-[#d8dee4] bg-white p-5">
          <div
            {...getRootProps()}
            className={`cursor-pointer rounded-[6px] border border-dashed p-8 text-center transition-colors ${
              isDragActive
                ? "border-[#0f766e] bg-[#e6f4f1]"
                : "border-[#d8dee4] hover:border-[#0f766e]"
            }`}
          >
            <input {...getInputProps()} />
            <UploadCloud className="mx-auto mb-2 text-[#405466]" size={24} />
            <p className="text-sm font-semibold">Drag and drop files</p>
            <p className="mt-1 text-xs text-[#718294]">
              PDF, JPG, PNG · Multiple files supported
            </p>
          </div>
        </section>

        <section className="mb-5 border border-[#d8dee4] bg-white p-5">
          <h2 className="mb-3 text-sm font-semibold">OCR processing pipeline</h2>
          <div className="flex flex-wrap items-center gap-2">
            {steps.map((label, idx) => (
              <div key={label} className="flex items-center gap-2">
                <span
                  className={`grid h-6 w-6 place-items-center rounded-full border text-[10px] ${
                    idx < step
                      ? "border-[#0f766e] bg-[#0f766e] text-white"
                      : idx === step
                        ? "active-breathe border-[#0f766e] text-[#0f766e]"
                        : "border-[#d8dee4] text-[#718294]"
                  }`}
                >
                  {idx + 1}
                </span>
                <span className="text-xs text-[#405466]">{label}</span>
                {idx < steps.length - 1 && <span className="h-px w-4 bg-[#d8dee4]" />}
              </div>
            ))}
          </div>
          <div className="mt-4">
            <Button onClick={runProcessing}>Process Application</Button>
          </div>
        </section>

        <section className="overflow-x-auto border border-[#d8dee4] bg-white">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="border-b border-[#d8dee4] bg-[#fbfcfd] text-[10px] uppercase tracking-[.1em] text-[#718294]">
              <tr>
                <th className="px-4 py-3">Document</th>
                <th className="px-4 py-3">Type</th>
                <th className="px-4 py-3">Size</th>
                <th className="px-4 py-3">Hash prefix</th>
                <th className="px-4 py-3">Upload status</th>
                <th className="px-4 py-3">Processing status</th>
              </tr>
            </thead>
            <tbody>
              {uploaded.length === 0 ? (
                <tr>
                  <td className="px-4 py-6 text-center text-[#718294]" colSpan={6}>
                    No files uploaded yet.
                  </td>
                </tr>
              ) : (
                uploaded.map((file) => (
                  <tr key={file.id} className="border-b border-[#edf0f2] last:border-0">
                    <td className="px-4 py-3 font-semibold text-[#12304a]">{file.name}</td>
                    <td className="px-4 py-3">{file.type}</td>
                    <td className="px-4 py-3">{file.size}</td>
                    <td className="mono px-4 py-3">SHA256: {file.hash}</td>
                    <td className="px-4 py-3 text-[#0f766e]">{file.uploadStatus}</td>
                    <td className="px-4 py-3">
                      {file.processingStatus === "SCANNED" ? (
                        <span className="text-[#0f766e]">SCANNED</span>
                      ) : file.processingStatus === "PROCESSING" ? (
                        <span className="text-[#b45309]">PROCESSING</span>
                      ) : (
                        <span className="text-[#405466]">READY</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </section>
      </main>
    </Shell>
  );
}
function ApplicationBar({ app }: { app: Application }) {
  return (
    <div className="sticky top-[64px] z-[5] flex flex-wrap items-center justify-between gap-3 border-b border-[#d8dee4] bg-white px-5 py-2.5">
      <div className="flex items-center gap-2 text-xs">
        <span className="text-[#718294]">Application ID</span>
        <span className="mono font-semibold">{app.id}</span>
        <CopyButton value={app.id} />
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span className="text-[#718294]">Policy version</span>
        <span className="mono font-semibold">{app.policy_version}</span>
        <span className="rounded-[3px] bg-[#e6f4f1] px-1.5 py-0.5 text-[10px] font-bold text-[#0f766e]">
          VERIFIED
        </span>
      </div>
    </div>
  );
}
function PageHead({
  eyebrow,
  title,
  sub,
}: {
  eyebrow: string;
  title: string;
  sub: string;
}) {
  return (
    <div className="mb-6">
      <div className="mb-2 text-[10px] font-bold uppercase tracking-[.16em] text-[#0f766e]">
        {eyebrow}
      </div>
      <h1 className="text-[26px] font-semibold tracking-[-.02em]">{title}</h1>
      <p className="mt-1 text-sm text-[#718294]">{sub}</p>
    </div>
  );
}
function Metric({
  label,
  value,
  trend,
  icon: Icon,
}: {
  label: string;
  value: string;
  trend: string;
  icon: typeof UsersRound;
}) {
  return (
    <div className="border border-[#d8dee4] bg-white p-4">
      <div className="flex items-start justify-between">
        <span className="text-xs font-semibold text-[#718294]">{label}</span>
        <Icon size={17} className="text-[#0f766e]" />
      </div>
      <div className="mt-4 flex items-end justify-between">
        <span className="tabular-nums text-[32px] font-semibold leading-none">
          {value}
        </span>
        <span className="flex items-center gap-1 text-[11px] font-semibold text-[#0f766e]">
          <ArrowUp size={13} />
          {trend}
        </span>
      </div>
      <div className="mt-3 h-1 overflow-hidden bg-[#eef2f4]">
        <div
          className="h-full bg-[#69b8b0]"
          style={{ width: `${Math.min(100, Number(value) * 1.5)}%` }}
        />
      </div>
    </div>
  );
}
function Dashboard() {
  const [filter, setFilter] = useState("");
  const rows = applications.filter((a) =>
    `${a.id} ${a.applicant_reference} ${a.status}`
      .toLowerCase()
      .includes(filter.toLowerCase()),
  );
  return (
    <Shell current="Dashboard">
      <main className="mx-auto max-w-[1500px] p-5 lg:p-8">
        <PageHead
          eyebrow="Overview / 23 August 2026"
          title="Decision operations"
          sub="Evidence-grounded applications across the PM-USP Scholarship scheme."
        />
        <div className="mb-8 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <Metric
            label="Total applications"
            value="24"
            trend="12%"
            icon={UsersRound}
          />
          <Metric label="Eligible" value="14" trend="8%" icon={BadgeCheck} />
          <Metric
            label="Needs review"
            value="05"
            trend="3 new"
            icon={AlertCircle}
          />
          <Metric label="Ineligible" value="05" trend="2%" icon={XCircle} />
        </div>
        <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="text-[18px] font-semibold">Application register</h2>
            <p className="text-xs text-[#718294]">
              Recent submissions requiring attention or ready for replay.
            </p>
          </div>
          <div className="flex gap-2">
            <div className="flex h-9 items-center gap-2 border border-[#d8dee4] bg-white px-2">
              <Search size={15} className="text-[#718294]" />
              <input
                value={filter}
                onChange={(e) => setFilter(e.target.value)}
                className="w-36 text-xs outline-none"
                placeholder="Filter register"
              />
            </div>
            <Button secondary>
              <Filter size={15} />
              Filters
            </Button>
          </div>
        </div>
        <div className="overflow-x-auto border border-[#d8dee4] bg-white">
          <table className="w-full min-w-[900px] text-left text-xs">
            <thead className="border-b border-[#d8dee4] bg-[#fbfcfd] text-[10px] uppercase tracking-[.1em] text-[#718294]">
              <tr>
                {[
                  "Application ID",
                  "Applicant reference",
                  "Scheme",
                  "Submitted",
                  "Docs",
                  "Evidence",
                  "Decision",
                  "Action",
                ].map((h) => (
                  <th key={h} className="px-4 py-3 font-bold">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((a) => (
                <tr
                  key={a.id}
                  className="border-b border-[#edf0f2] last:border-0 hover:bg-[#f7f9fa]"
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/applications/${a.id}`}
                      className="mono font-semibold text-[#0f766e] hover:underline"
                    >
                      {a.id}
                    </Link>
                  </td>
                  <td className="mono px-4 py-3 text-[#405466]">
                    {a.applicant_reference}
                  </td>
                  <td className="px-4 py-3">PM-USP Scholarship</td>
                  <td className="mono px-4 py-3 text-[#718294]">
                    {a.submitted_at.slice(11, 16)} UTC
                  </td>
                  <td className="px-4 py-3">{a.documents}/5</td>
                  <td className="px-4 py-3">
                    <Quality quality={a.evidence_quality} />
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={a.status} />
                  </td>
                  <td className="px-4 py-3">
                    <Link
                      href={`/applications/${a.id}/replay`}
                      className="font-semibold text-[#2563eb] hover:underline"
                    >
                      Open case <ChevronRight size={13} className="inline" />
                    </Link>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </main>
    </Shell>
  );
}

function CaseNav({ app, active }: { app: Application; active: View }) {
  const tabs: [string, View, string][] = [
    ["Overview", "dashboard", ""],
    ["Evidence", "evidence", "/evidence"],
    ["Decision", "decision", "/decision"],
    ["Review", "review", "/review"],
    ["Replay", "replay", "/replay"],
  ];
  return (
    <>
      <ApplicationBar app={app} />
      <div className="border-b border-[#d8dee4] bg-white px-5">
        <div className="flex gap-6 overflow-x-auto">
          {tabs.map(([label, view, suffix]) => (
            <Link
              key={label}
              href={`/applications/${app.id}${suffix}`}
              className={`whitespace-nowrap border-b-2 py-3 text-xs font-semibold ${active === view ? "border-[#0f766e] text-[#0f766e]" : "border-transparent text-[#718294] hover:text-[#12304a]"}`}
            >
              {label}
            </Link>
          ))}
        </div>
      </div>
    </>
  );
}
function Overview({ app }: { app: Application }) {
  return (
    <Shell current="Applications">
      <CaseNav app={app} active="dashboard" />
      <main className="mx-auto max-w-[1500px] p-5 lg:p-8">
        <PageHead
          eyebrow="Application case file"
          title={app.id}
          sub="A single auditable record from submission through final decision."
        />
        <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
          <section className="border border-[#d8dee4] bg-white p-5">
            <div className="mb-5 flex items-start justify-between">
              <div>
                <FieldLabel>Current outcome</FieldLabel>
                <div className="mt-2 flex items-center gap-3 text-2xl font-semibold">
                  <StatusBadge status={app.status} />
                </div>
              </div>
              <Button href={`/applications/${app.id}/replay`} secondary>
                <History size={15} />
                Replay case
              </Button>
            </div>
            <div className="grid grid-cols-2 gap-y-5 sm:grid-cols-3">
              <div>
                <FieldLabel>Applicant reference</FieldLabel>
                <span className="mono text-xs">{app.applicant_reference}</span>
              </div>
              <div>
                <FieldLabel>Scheme</FieldLabel>
                <span className="text-xs">PM-USP Scholarship</span>
              </div>
              <div>
                <FieldLabel>Submitted</FieldLabel>
                <span className="mono text-xs">23 Aug 2026, 09:21</span>
              </div>
              <div>
                <FieldLabel>Policy version</FieldLabel>
                <span className="mono text-xs">{app.policy_version}</span>
              </div>
              <div>
                <FieldLabel>Documents</FieldLabel>
                <span className="text-xs">{app.documents} required</span>
              </div>
              <div>
                <FieldLabel>Evidence quality</FieldLabel>
                <Quality quality={app.evidence_quality} />
              </div>
            </div>
          </section>
          <section className="border border-[#d8dee4] bg-white p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <FieldLabel>Lifecycle</FieldLabel>
                <h2 className="text-[17px] font-semibold">
                  Traceability status
                </h2>
              </div>
              <Activity size={18} className="text-[#0f766e]" />
            </div>
            {[
              "Documents received",
              "Fields validated",
              "Rules evaluated",
              "Decision recorded",
            ].map((step, i) => (
              <div
                key={step}
                className="flex items-center gap-3 border-b border-[#edf0f2] py-3 last:border-0"
              >
                <span className="grid h-6 w-6 place-items-center rounded-full bg-[#e6f4f1] text-[#0f766e]">
                  <Check size={14} />
                </span>
                <span className="text-xs">{step}</span>
                <span className="mono ml-auto text-[10px] text-[#718294]">
                  {["09:21", "09:22", "09:23", "09:24"][i]}
                </span>
              </div>
            ))}
          </section>
        </div>
        <div className="mt-5 grid gap-4 sm:grid-cols-3">
          <Metric
            label="Extracted fields"
            value={String(app.fields)}
            trend="validated"
            icon={FileCheck2}
          />
          <Metric
            label="Review issues"
            value={String(app.review_issues).padStart(2, "0")}
            trend="open"
            icon={AlertCircle}
          />
          <Metric
            label="Audit events"
            value="12"
            trend="verified"
            icon={History}
          />
        </div>
      </main>
    </Shell>
  );
}
function Evidence({ app }: { app: Application }) {
  const [selected, setSelected] = useState(app.fields_data[0]);
  return (
    <Shell current="Applications">
      <CaseNav app={app} active="evidence" />
      <main className="mx-auto max-w-[1500px] p-5 lg:p-8">
        <PageHead
          eyebrow="Evidence review"
          title="Extracted fields"
          sub="Every normalized value remains linked to its source document and verbatim evidence."
        />
        <div className="grid gap-4 xl:grid-cols-[minmax(360px,0.75fr)_minmax(0,1.25fr)]">
          <section className="space-y-3">
            {(app.fields_data.length
              ? app.fields_data
              : applications[0].fields_data
            ).map((field) => (
              <button
                key={field.field_name}
                onClick={() => setSelected(field)}
                className={`evidence-flash w-full border bg-white p-4 text-left ${selected.field_name === field.field_name ? "border-l-2 border-l-[#0f766e] border-[#b8c9cc]" : "border-[#d8dee4] hover:border-[#9cb8ba]"}`}
              >
                <div className="mb-3 flex items-start justify-between">
                  <div>
                    <FieldLabel>{field.label}</FieldLabel>
                    <div className="text-[16px] font-semibold">
                      {field.value}
                    </div>
                  </div>
                  <Quality quality={field.confidence} />
                </div>
                <div className="grid grid-cols-2 gap-3 border-t border-[#edf0f2] pt-3">
                  <div>
                    <FieldLabel>OCR quality</FieldLabel>
                    <span className="text-xs">{field.ocr_quality}%</span>
                  </div>
                  <div>
                    <FieldLabel>Evidence match</FieldLabel>
                    <span className="text-xs">{field.match}</span>
                  </div>
                  <div>
                    <FieldLabel>Source</FieldLabel>
                    <span className="mono text-[10px]">{field.source}</span>
                  </div>
                  <div>
                    <FieldLabel>Validation</FieldLabel>
                    <span className="text-xs text-[#0f766e]">
                      {field.validation}
                    </span>
                  </div>
                </div>
                <div className="mt-3">
                  <Quote>{field.quote}</Quote>
                </div>
                <div className="mt-3 text-right text-xs font-semibold text-[#2563eb]">
                  Open source evidence{" "}
                  <ChevronRight size={13} className="inline" />
                </div>
              </button>
            ))}
          </section>
          <section className="min-h-[560px] border border-[#d8dee4] bg-white">
            <div className="flex h-10 items-center justify-between border-b border-[#d8dee4] px-3 text-xs text-[#405466]">
              <div className="flex gap-3">
                <button aria-label="Zoom out">
                  <ArrowDown size={15} />
                </button>
                <button aria-label="Zoom in">
                  <ArrowUp size={15} />
                </button>
                <button>Fit width</button>
              </div>
              <span className="mono">Page {selected.page} of 4</span>
              <button aria-label="Search document">
                <Search size={15} />
              </button>
            </div>
            <div className="flex min-h-[520px] items-center justify-center bg-[#eef1f3] p-6">
              <div className="relative min-h-[440px] w-full max-w-[620px] border border-[#d8dee4] bg-white p-8 shadow-[0_2px_8px_rgba(18,48,74,.08)]">
                <div className="mb-7 flex items-start justify-between border-b border-[#d8dee4] pb-4">
                  <div>
                    <div className="font-serif text-lg font-bold">
                      Government of India
                    </div>
                    <div className="text-[10px] uppercase tracking-[.12em] text-[#718294]">
                      Income certificate
                    </div>
                  </div>
                  <span className="mono text-[10px] text-[#718294]">
                    DOC-103
                  </span>
                </div>
                <div className="space-y-3 text-[11px] leading-5 text-[#405466]">
                  <div className="h-2 w-3/4 bg-[#edf0f2]" />
                  <div className="h-2 w-full bg-[#edf0f2]" />
                  <div className="mt-8 border border-[#f1d5a9] bg-[#fff8ec] p-3 font-serif text-[13px] italic text-[#405466]">
                    {selected.quote}
                  </div>
                  <div className="h-2 w-5/6 bg-[#edf0f2]" />
                  <div className="h-2 w-2/3 bg-[#edf0f2]" />
                </div>
                <span className="absolute bottom-4 right-8 mono text-[10px] text-[#718294]">
                  {selected.page}
                </span>
              </div>
            </div>
          </section>
        </div>
      </main>
    </Shell>
  );
}

function Decision({ app }: { app: Application }) {
  return (
    <Shell current="Applications">
      <CaseNav app={app} active="decision" />
      <main className="mx-auto max-w-[1500px] p-5 lg:p-8">
        <div className="mb-7 border-b border-[#d8dee4] bg-white px-1 py-5">
          <FieldLabel>Final outcome</FieldLabel>
          <div className="flex flex-wrap items-center gap-4">
            <h1 className="text-[32px] font-semibold text-[#0f766e]">
              ELIGIBLE
            </h1>
            <StatusBadge status="ELIGIBLE" />
            <span className="text-xs text-[#718294]">
              Decision version <span className="mono">DEC-2026-0019</span>
            </span>
          </div>
        </div>
        <div className="mb-6 grid gap-3 sm:grid-cols-3">
          <div className="border border-[#d8dee4] bg-white p-4">
            <FieldLabel>Decision mode</FieldLabel>
            <div className="text-sm font-semibold">Automated</div>
          </div>
          <div className="border border-[#d8dee4] bg-white p-4">
            <FieldLabel>Evidence quality</FieldLabel>
            <Quality quality="HIGH" />
          </div>
          <div className="border border-[#d8dee4] bg-white p-4">
            <FieldLabel>Policy version</FieldLabel>
            <div className="mono text-xs">{app.policy_version}</div>
          </div>
        </div>
        <div className="grid gap-5 xl:grid-cols-[1.5fr_1fr]">
          <section>
            <div className="mb-3 flex items-end justify-between">
              <div>
                <h2 className="text-[18px] font-semibold">Rule evaluation</h2>
                <p className="text-xs text-[#718294]">
                  Six frozen rules evaluated against validated evidence.
                </p>
              </div>
              <span className="mono text-xs text-[#718294]">6 / 6 passed</span>
            </div>
            <div className="overflow-x-auto border border-[#d8dee4] bg-white">
              <table className="w-full min-w-[680px] text-left text-xs">
                <thead className="border-b border-[#d8dee4] bg-[#fbfcfd] text-[10px] uppercase tracking-[.1em] text-[#718294]">
                  <tr>
                    <th className="px-4 py-3">Rule</th>
                    <th className="px-4 py-3">Input</th>
                    <th className="px-4 py-3">Result</th>
                    <th className="px-4 py-3">Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {rules.map((rule) => (
                    <tr
                      key={rule.code}
                      className="border-b border-[#edf0f2] last:border-0"
                    >
                      <td className="px-4 py-3">
                        <span className="mono text-[10px] font-semibold">
                          {rule.code}
                        </span>
                        <div className="mt-1 text-[#718294]">{rule.label}</div>
                      </td>
                      <td className="px-4 py-3 mono">{rule.input}</td>
                      <td className="px-4 py-3">
                        <span className="font-bold text-[#0f766e]">
                          {rule.result}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-[#405466]">
                        {rule.explanation}
                        <div className="mt-1 text-[10px] text-[#2563eb]">
                          {rule.evidence}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          <section className="border border-[#d8dee4] bg-white p-5">
            <FieldLabel>Decision explanation</FieldLabel>
            <h2 className="mb-4 text-[20px] font-semibold">
              Why this outcome?
            </h2>
            <p className="text-[16px] leading-7 text-[#405466]">
              The application satisfies all six eligibility requirements. Every
              input was validated against a source document and evaluated under{" "}
              <span className="mono text-[13px]">{app.policy_version}</span>.
            </p>
            <div className="mt-5 border-l-2 border-[#0f766e] pl-4 text-sm leading-6 text-[#405466]">
              The decision can be reconstructed from the evidence, rule inputs,
              and policy version recorded in the audit chain.
            </div>
          </section>
        </div>
      </main>
    </Shell>
  );
}

function Review({ app }: { app: Application }) {
  const [submitted, setSubmitted] = useState(false);
  return (
    <Shell current="Applications">
      <CaseNav app={app} active="review" />
      <main className="mx-auto max-w-[1100px] p-5 lg:p-8">
        <PageHead
          eyebrow="Human oversight"
          title="Review required"
          sub="Resolve the evidence conflict before a final decision is recorded."
        />
        {submitted ? (
          <div className="border border-[#b8d8d3] bg-[#e6f4f1] p-6">
            <div className="flex items-center gap-3 text-[#0f766e]">
              <BadgeCheck size={22} />
              <h2 className="text-lg font-semibold">Human Confirmed</h2>
            </div>
            <div className="mt-4 grid gap-3 text-xs sm:grid-cols-3">
              <div>
                <FieldLabel>Reviewer</FieldLabel>
                <span className="mono">reviewer_004</span>
              </div>
              <div>
                <FieldLabel>Time</FieldLabel>
                <span className="mono">14:32:08 UTC</span>
              </div>
              <div>
                <FieldLabel>Reason</FieldLabel>
                <span>OCR error</span>
              </div>
            </div>
            <div className="mt-5">
              <Button href={`/applications/${app.id}/replay`}>
                View updated replay <History size={15} />
              </Button>
            </div>
          </div>
        ) : (
          <>
            <div className="mb-5 border border-[#d8dee4] bg-white p-5">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <FieldLabel>Conflict · family_income</FieldLabel>
                  <h2 className="text-[18px] font-semibold">
                    Applicant income
                  </h2>
                </div>
                <StatusBadge status="NEEDS_REVIEW" />
              </div>
              <div className="grid gap-3 md:grid-cols-2">
                <div className="border border-[#d8dee4] p-4">
                  <FieldLabel>Source A · Income certificate</FieldLabel>
                  <div className="mt-2 text-xl font-semibold">₹4,80,000</div>
                  <p className="mt-2 text-xs text-[#718294]">
                    OCR quality 88% · partial match
                  </p>
                  <div className="mt-3">
                    <Quote>Annual family income: Rs. 4,80,000</Quote>
                  </div>
                </div>
                <div className="border border-[#d8dee4] p-4">
                  <FieldLabel>Source B · Bank statement</FieldLabel>
                  <div className="mt-2 text-xl font-semibold">₹4,08,000</div>
                  <p className="mt-2 text-xs text-[#718294]">
                    OCR quality 96% · exact match
                  </p>
                  <div className="mt-3">
                    <Quote>
                      Annual credits indicate family income of Rs. 4,08,000
                    </Quote>
                  </div>
                </div>
              </div>
            </div>
            <div className="border border-[#d8dee4] bg-white p-5">
              <FieldLabel>Reviewer action</FieldLabel>
              <div className="grid gap-4 md:grid-cols-2">
                <label className="text-xs font-semibold">
                  Reason
                  <select className="mt-2 h-10 w-full rounded-[4px] border border-[#d8dee4] bg-white px-3 text-xs">
                    <option>OCR error</option>
                    <option>Document conflict</option>
                    <option>Source document clearer</option>
                    <option>Insufficient evidence</option>
                  </select>
                </label>
                <label className="text-xs font-semibold">
                  Additional explanation
                  <textarea
                    required
                    className="mt-2 h-10 w-full rounded-[4px] border border-[#d8dee4] px-3 py-2 text-xs"
                    placeholder="Required reviewer rationale"
                  />
                </label>
              </div>
              <div className="mt-5 flex flex-wrap gap-2">
                <Button onClick={() => setSubmitted(true)}>
                  <Check size={15} />
                  Accept Source B
                </Button>
                <Button secondary>Accept Source A</Button>
                <Button secondary>
                  <FileText size={15} />
                  Request document
                </Button>
              </div>
            </div>
          </>
        )}
      </main>
    </Shell>
  );
}

function Replay({ app }: { app: Application }) {
  const [expanded, setExpanded] = useState<number | null>(11);
  const [verified, setVerified] = useState(true);
  return (
    <Shell current="Applications">
      <CaseNav app={app} active="replay" />
      <main className="mx-auto max-w-[1180px] p-5 lg:p-8">
        <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div>
            <PageHead
              eyebrow="Forensic reconstruction"
              title="Replay the decision"
              sub="A complete, immutable record of how this case moved from document to outcome."
            />
          </div>
          <button
            onClick={() => setVerified(!verified)}
            className={`signature-draw flex items-center gap-2 rounded-[5px] px-4 py-3 text-xs font-bold tracking-wide text-white ${verified ? "bg-[#0f766e]" : "bg-[#405466]"}`}
          >
            <ShieldCheck size={19} />
            {verified ? "AUDIT CHAIN VERIFIED" : "VERIFY AUDIT CHAIN"}
          </button>
        </div>
        {verified && (
          <div className="mb-7 grid gap-3 border border-[#b8d8d3] bg-[#e6f4f1] p-4 text-xs sm:grid-cols-4">
            <div>
              <FieldLabel>Hash chain</FieldLabel>
              <b className="text-[#0f766e]">Valid</b>
            </div>
            <div>
              <FieldLabel>Events verified</FieldLabel>
              <b>17 / 17</b>
            </div>
            <div>
              <FieldLabel>Latest hash</FieldLabel>
              <span className="mono">
                94af3c92f7...8d21 <CopyButton value="94af3c92f7c82a8d21" />
              </span>
            </div>
            <div>
              <FieldLabel>Verified at</FieldLabel>
              <span className="mono">13:41:02 UTC</span>
            </div>
          </div>
        )}
        <div className="mb-8 flex items-center overflow-x-auto border-y border-[#d8dee4] bg-white py-4">
          {[
            "Documents",
            "OCR",
            "Extraction",
            "Evidence",
            "Rules",
            "Initial decision",
            "Human review",
            "Final decision",
          ].map((stage, i) => (
            <div key={stage} className="flex min-w-[110px] items-center">
              <div className="text-center">
                <span className="mx-auto grid h-7 w-7 place-items-center rounded-full border border-[#0f766e] bg-[#e6f4f1] text-[#0f766e]">
                  <Check size={14} />
                </span>
                <span className="mt-2 block text-[10px] font-semibold">
                  {stage}
                </span>
              </div>
              {i < 7 && <span className="mx-2 h-px w-8 bg-[#69b8b0]" />}
            </div>
          ))}
        </div>
        <section>
          <div className="mb-4 flex items-end justify-between">
            <div>
              <h2 className="text-[18px] font-semibold">Audit timeline</h2>
              <p className="text-xs text-[#718294]">
                Expand an event to inspect the exact snapshot used at decision
                time.
              </p>
            </div>
            <span className="mono text-[11px] text-[#718294]">
              12 events · hash-linked
            </span>
          </div>
          <div className="border-l-2 border-[#d8dee4] pl-6">
            {auditEvents.map(([time, label, type, kind], i) => (
              <div key={`${time}-${label}`} className="relative">
                <span
                  className={`absolute -left-[32px] top-5 h-3 w-3 rounded-full border-2 border-white ${kind === "review" ? "bg-[#b45309]" : "bg-[#0f766e]"}`}
                />
                <button
                  onClick={() => setExpanded(expanded === i ? null : i)}
                  className={`flex w-full items-center gap-4 border-b border-[#edf0f2] px-3 py-4 text-left ${expanded === i ? "bg-[#f7f9fa]" : "bg-white"}`}
                >
                  <span className="mono w-16 text-[11px] text-[#718294]">
                    {time}
                  </span>
                  <span className="flex-1 text-sm font-semibold">{label}</span>
                  <span className="mono hidden text-[10px] text-[#718294] sm:block">
                    {type}
                  </span>
                  {expanded === i ? (
                    <ChevronDown size={16} />
                  ) : (
                    <ChevronRight size={16} />
                  )}
                </button>
                {expanded === i && (
                  <div className="evidence-flash border-b border-[#d8dee4] bg-white px-4 py-4 pl-[80px] text-xs text-[#405466]">
                    <div className="grid gap-4 sm:grid-cols-2">
                      <div>
                        <FieldLabel>Event hash</FieldLabel>
                        <div className="mono">
                          e4a91d20f7c8... <CopyButton value="e4a91d20f7c8" />
                        </div>
                      </div>
                      <div>
                        <FieldLabel>Actor</FieldLabel>
                        <div>
                          {kind === "review"
                            ? "reviewer_004"
                            : "system / orchestration"}
                        </div>
                      </div>
                      <div>
                        <FieldLabel>Evidence snapshot</FieldLabel>
                        <div className="mt-1">
                          {label === "Field extraction completed" ? (
                            <Quote>Annual family income: Rs. 4,08,000</Quote>
                          ) : (
                            "Snapshot verified against the policy version active at event time."
                          )}
                        </div>
                      </div>
                      <div>
                        <FieldLabel>Hash chain</FieldLabel>
                        <div className="mono leading-6">
                          prev 7d8c...a91e
                          <br />
                          <ArrowDown
                            size={14}
                            className="inline text-[#0f766e]"
                          />
                          <br />
                          current e4a9...f7c8
                        </div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </section>
      </main>
    </Shell>
  );
}

function AdminView({
  view,
}: {
  view: "policies" | "audit" | "reports" | "upload";
}) {
  const title =
    view === "policies"
      ? "Policy registry"
      : view === "audit"
        ? "Global audit log"
        : view === "reports"
          ? "Operational reports"
          : "New application";
  return (
    <Shell
      current={
        view === "policies"
          ? "Policies"
          : view === "audit"
            ? "Audit log"
            : view === "reports"
              ? "Reports"
              : "Applications"
      }
    >
      <main className="mx-auto max-w-[1500px] p-5 lg:p-8">
        <PageHead
          eyebrow="Control plane"
          title={title}
          sub={
            view === "reports"
              ? "A restrained view of system performance and human intervention."
              : "Search, inspect, and manage the evidence decision lifecycle."
          }
        />
        {view === "reports" ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {[
              ["Eligible rate", "58.3%"],
              ["Review rate", "20.8%"],
              ["Avg processing", "02:41"],
              ["Reviewer intervention", "12.5%"],
            ].map(([l, v]) => (
              <Metric
                key={l}
                label={l}
                value={v}
                trend="vs last week"
                icon={Gauge}
              />
            ))}
            <div className="border border-[#d8dee4] bg-white p-5 sm:col-span-2 lg:col-span-4">
              <h2 className="text-[18px] font-semibold">
                Outcome distribution
              </h2>
              <div className="mt-8 flex h-40 items-end gap-8 border-b border-[#d8dee4] px-8">
                <div className="w-20 bg-[#69b8b0]" style={{ height: "78%" }} />
                <div className="w-20 bg-[#d6a252]" style={{ height: "35%" }} />
                <div className="w-20 bg-[#d47b7b]" style={{ height: "26%" }} />
              </div>
              <div className="mt-3 flex gap-8 text-xs text-[#405466]">
                <span>Eligible</span>
                <span>Review</span>
                <span>Ineligible</span>
              </div>
            </div>
          </div>
        ) : (
          <div className="overflow-x-auto border border-[#d8dee4] bg-white">
            <table className="w-full min-w-[850px] text-left text-xs">
              <thead className="border-b border-[#d8dee4] bg-[#fbfcfd] text-[10px] uppercase tracking-[.1em] text-[#718294]">
                <tr>
                  {(view === "policies"
                    ? [
                        "Scheme",
                        "Version",
                        "Effective from",
                        "Rules",
                        "Status",
                        "Actions",
                      ]
                    : [
                        "Timestamp",
                        "Application",
                        "Event",
                        "Actor",
                        "Policy",
                        "Hash",
                        "Verification",
                      ]
                  ).map((h) => (
                    <th key={h} className="px-4 py-3">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(view === "policies"
                  ? [
                      [
                        "PM-USP Scholarship",
                        "CSSS-Demo-v1.1",
                        "01 Aug 2026",
                        "6",
                        "PUBLISHED",
                      ],
                      [
                        "PM-USP Scholarship",
                        "CSSS-Demo-v1.0",
                        "01 Apr 2026",
                        "5",
                        "RETIRED",
                      ],
                      [
                        "Housing Support Scheme",
                        "HSS-Demo-v0.4",
                        "15 Jul 2026",
                        "8",
                        "DRAFT",
                      ],
                    ]
                  : auditEvents
                      .slice(0, 8)
                      .map((e) => [
                        e[0],
                        "APP-00016",
                        e[1],
                        e[3] === "review" ? "reviewer_004" : "system",
                        "CSSS-Demo-v1.1",
                        "94af3c...8d21",
                        "VERIFIED",
                      ])
                ).map((row, i) => (
                  <tr
                    key={i}
                    className="border-b border-[#edf0f2] last:border-0"
                  >
                    {row.map((cell, j) => (
                      <td key={j} className={`px-4 py-3 ${j === 1 || j === 5 ? "mono" : ""} ${j === 4 || (view === "audit" && j === 6) ? "text-[#0f766e]" : ""}`}>
                        {cell}
                      </td>
                    ))}
                    {view === "policies" && <td className="px-4 py-3"><span className="font-semibold text-[#2563eb]">View policy</span></td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </main>
    </Shell>
  );
}

export default function SynapseApp({
  view,
  applicationId = "APP-00016",
}: Props) {
  const app =
    applications.find((item) => item.id === applicationId) ?? applications[0];
  if (view === "dashboard") return <Dashboard />;
  if (view === "evidence") return <Evidence app={app} />;
  if (view === "decision") return <Decision app={app} />;
  if (view === "review") return <Review app={applications[2]} />;
  if (view === "replay") return <Replay app={app} />;
  if (view === "upload") return <UploadView />;
  if (
    view === "policies" ||
    view === "audit" ||
    view === "reports"
  )
    return <AdminView view={view} />;
  return <Overview app={app} />;
}
