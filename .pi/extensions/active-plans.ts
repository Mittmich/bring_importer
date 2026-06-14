/**
 * Active Plans Extension
 *
 * Scans .pi/plans/ on every turn and injects a summary of plans with
 * status: active (and a heads-up for status: draft) into the system prompt.
 * This keeps the agent aware of in-flight work without the user having to
 * mention it.
 *
 * Conventions assumed (kept in sync with .pi/plans/_template.md and the
 * /plan and /plan-execute prompt templates):
 *   - File: .pi/plans/YYYY-MM-DD-<slug>.md
 *   - Frontmatter fields: title, status, created, updated
 *   - Status values: draft | active | done | archived
 *   - Steps are markdown checkboxes: - [ ] open, - [x] done
 *
 * Disable for one session with:  pi --no-extension extensions/active-plans.ts
 * Or remove from .pi/settings.json to disable project-wide.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

const PLANS_DIR = path.join(process.cwd(), ".pi", "plans");

interface PlanInfo {
	file: string;
	title: string;
	status: string;
	updated: string;
	openSteps: number;
	doneSteps: number;
}

function listMarkdownFiles(dir: string): string[] {
	if (!fs.existsSync(dir)) return [];
	return fs
		.readdirSync(dir, { withFileTypes: true })
		.filter((e) => e.isFile() && e.name.endsWith(".md") && !e.name.startsWith("_"))
		.map((e) => path.join(dir, e.name));
}

/**
 * Minimal frontmatter + checkbox parser. We intentionally avoid a YAML
 * dependency to keep the extension zero-dep. The plan files are written by
 * our own templates, so a few well-defined regexes are sufficient.
 */
function parsePlan(filePath: string): PlanInfo | null {
	const text = fs.readFileSync(filePath, "utf8");
	const lines = text.split("\n");

	// Frontmatter is the block between the first two "---" lines.
	let inFrontmatter = false;
	let title = "";
	let status = "";
	let updated = "";
	for (const line of lines) {
		if (line.trim() === "---") {
			if (!inFrontmatter) {
				inFrontmatter = true;
				continue;
			}
			break; // end of frontmatter
		}
		if (!inFrontmatter) continue;

		const m = line.match(/^\s*(title|status|updated)\s*:\s*(.*?)\s*$/);
		if (!m) continue;
		const [, key, value] = m;
		const cleaned = value.replace(/^["']|["']$/g, "").trim();
		if (key === "title") title = cleaned;
		else if (key === "status") status = cleaned;
		else if (key === "updated") updated = cleaned;
	}

	// Fall back to the first H1 if no title in frontmatter.
	if (!title) {
		const h1 = lines.find((l) => l.startsWith("# "));
		if (h1) title = h1.slice(2).trim();
	}
	if (!title) title = path.basename(filePath, ".md");

	// Count step checkboxes across the body (skip frontmatter).
	let openSteps = 0;
	let doneSteps = 0;
	let pastFrontmatter = false;
	let fenceDepth = 0;
	for (const line of lines) {
		if (!pastFrontmatter) {
			if (line.trim() === "---") fenceDepth++;
			if (fenceDepth >= 2) pastFrontmatter = true;
			continue;
		}
		const t = line.trim();
		if (/^- \[ \]/.test(t)) openSteps++;
		else if (/^- \[x\]/i.test(t)) doneSteps++;
	}

	return {
		file: path.relative(process.cwd(), filePath),
		title,
		status: status || "draft",
		updated,
		openSteps,
		doneSteps,
	};
}

function formatPrompt(actives: PlanInfo[], drafts: PlanInfo[]): string {
	if (actives.length === 0 && drafts.length === 0) return "";

	const lines: string[] = [];
	lines.push("## Active plans in this repo");
	lines.push("");
	lines.push(
		"Plans are markdown files under `.pi/plans/`. They are the source of truth for in-flight work.",
	);
	lines.push(
		"Use `read` to open a plan before making changes that fall under it. Use `/plan-execute <name>` to resume execution.",
	);
	lines.push("");

	if (actives.length > 0) {
		lines.push("### Active (executing)");
		for (const p of actives) {
			const total = p.openSteps + p.doneSteps;
			const date = p.updated ? ` (updated ${p.updated})` : "";
			lines.push(`- **${p.title}** — \`${p.file}\`${date} — ${p.doneSteps}/${total} steps done`);
		}
		lines.push("");
	}

	if (drafts.length > 0) {
		lines.push("### Drafts (awaiting approval — not yet executing)");
		for (const p of drafts) {
			const date = p.updated ? ` (updated ${p.updated})` : "";
			lines.push(`- **${p.title}** — \`${p.file}\`${date}`);
		}
		lines.push("");
	}

	lines.push(
		"Before starting new work, check whether it overlaps an active plan. If it does, open the plan and follow it. If it doesn't, either start a new plan with `/plan <topic>` or proceed if the change is trivial.",
	);

	return lines.join("\n");
}

export default function activePlansExtension(pi: ExtensionAPI): void {
	pi.on("before_agent_start", async (event) => {
		const files = listMarkdownFiles(PLANS_DIR);
		if (files.length === 0) return;

		const plans: PlanInfo[] = [];
		for (const f of files) {
			try {
				const info = parsePlan(f);
				if (info) plans.push(info);
			} catch {
				// Skip malformed files silently — don't crash the agent.
			}
		}

		const actives = plans
			.filter((p) => p.status === "active")
			.sort((a, b) => b.updated.localeCompare(a.updated));
		const drafts = plans
			.filter((p) => p.status === "draft")
			.sort((a, b) => b.updated.localeCompare(a.updated));

		const block = formatPrompt(actives, drafts);
		if (!block) return;

		return {
			systemPrompt: event.systemPrompt + "\n\n" + block + "\n",
		};
	});
}
