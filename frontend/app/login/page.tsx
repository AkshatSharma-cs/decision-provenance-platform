"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Eye, EyeOff, Moon, ShieldCheck, Sun } from "lucide-react";

export default function LoginPage() {
	const [show, setShow] = useState(false);
	const [dark, setDark] = useState(false);
	const [preferencesReady, setPreferencesReady] = useState(false);
	const [loadingRole, setLoadingRole] = useState<"ADMIN" | "USER" | null>(
		null,
	);
	const router = useRouter();

	useEffect(() => {
		const frame = window.requestAnimationFrame(() => {
			setDark(window.localStorage.getItem("synapse-theme") === "dark");
			setPreferencesReady(true);
		});
		return () => window.cancelAnimationFrame(frame);
	}, []);

	useEffect(() => {
		if (!preferencesReady) return;
		window.localStorage.setItem("synapse-theme", dark ? "dark" : "light");
	}, [dark, preferencesReady]);

	const signInAs = (role: "ADMIN" | "USER") => {
		setLoadingRole(role);
		window.localStorage.setItem("synapse-role", role);
		setTimeout(() => {
			router.push(role === "USER" ? "/upload" : "/");
		}, 300);
	};

	const cardClass = dark
		? "border-[#294253] bg-[#172b3b] text-[#e8f0f3]"
		: "border-[#d8dee4] bg-white text-[#12304a]";
	const mutedClass = dark ? "text-[#b6c7d1]" : "text-[#718294]";
	const inputClass = dark
		? "border-[#385567] bg-[#102230] text-[#e8f0f3]"
		: "border-[#d8dee4] bg-white text-[#12304a]";
	const secondaryButtonClass = dark
		? "border-[#385567] bg-[#102230] text-[#e8f0f3] hover:bg-[#172b3b]"
		: "border-[#d8dee4] bg-white text-[#12304a] hover:bg-[#f5f7fa]";

	return (
		<main
			data-theme={dark ? "dark" : "light"}
			style={{ backgroundColor: dark ? "#0e1c28" : "#f5f7fa" }}
			className="grid min-h-screen place-items-center bg-[#f5f7fa] p-5"
		>
			<section className={`relative w-full max-w-[440px] border p-7 ${cardClass}`}>
				<button
					onClick={() => setDark(!dark)}
					className={`absolute right-5 top-5 grid h-8 w-8 place-items-center rounded-[4px] border transition-colors hover:border-[#0f766e] hover:text-[#0f766e] ${dark ? "border-[#385567] text-[#b6c7d1]" : "border-[#d8dee4] text-[#405466]"}`}
					aria-label={dark ? "Switch to light theme" : "Switch to dark theme"}
					title={dark ? "Light theme" : "Dark theme"}
				>
					{dark ? <Sun size={16} /> : <Moon size={16} />}
				</button>
				<div className="mb-8 flex items-center gap-3">
					<span className="grid h-9 w-9 place-items-center rounded-[4px] border border-[#69b8b0] text-[#0f766e]">
						<ShieldCheck size={20} />
					</span>
					<div>
						<div className="mono text-[17px] font-bold">SYNAPSE</div>
						<div className={`text-[10px] ${mutedClass}`}>
							Decision provenance layer
						</div>
					</div>
				</div>
				<h1 className="text-[22px] font-semibold">Demo sign in</h1>
				<p className={`mt-1 text-xs ${mutedClass}`}>
					Choose a role for the hackathon demo.
				</p>

				<form className="mt-7 space-y-4" onSubmit={(e) => e.preventDefault()}>
					<label className="block text-xs font-semibold">
						Work email
						<input
							type="email"
							required
							defaultValue="auditor@synapse.gov"
							className={`mt-2 h-10 w-full rounded-[4px] border px-3 text-sm ${inputClass}`}
						/>
					</label>
					<label className="block text-xs font-semibold">
						Password
						<div className={`mt-2 flex h-10 items-center border px-3 ${inputClass}`}>
							<input
								required
								type={show ? "text" : "password"}
								defaultValue="demo-password"
								className={`w-full bg-transparent text-sm outline-none ${dark ? "placeholder:text-[#6f8796]" : ""}`}
							/>
							<button
								type="button"
								aria-label="Show password"
								onClick={() => setShow(!show)}
								className={mutedClass}
							>
								{show ? <EyeOff size={16} /> : <Eye size={16} />}
							</button>
						</div>
					</label>
					<label className={`flex items-center gap-2 text-xs ${mutedClass}`}>
						<input type="checkbox" defaultChecked /> Remember this device
					</label>

					<button
						type="button"
						disabled={loadingRole !== null}
						onClick={() => signInAs("ADMIN")}
						className="flex h-10 w-full items-center justify-center rounded-[4px] bg-[#0f766e] text-xs font-bold text-white hover:bg-[#0c625d] disabled:opacity-60"
					>
						{loadingRole === "ADMIN" ? "Signing in..." : "Sign in as admin"}
					</button>
					<button
						type="button"
						disabled={loadingRole !== null}
						onClick={() => signInAs("USER")}
						className={`flex h-10 w-full items-center justify-center rounded-[4px] border text-xs font-bold disabled:opacity-60 ${secondaryButtonClass}`}
					>
						{loadingRole === "USER"
							? "Opening applicant upload..."
							: "Sign in as user (OCR upload)"}
					</button>
				</form>
				<p className={`mt-6 text-center text-[10px] ${mutedClass}`}>
					Mock environment · synthetic records only
				</p>
			</section>
		</main>
	);
}
