#!/usr/bin/env python3
"""
Skills Assigner

Analyzes goal files and SDP section specs to determine which skills
are needed for each goal. Writes skill assignments into goal frontmatter
and generates a skills map for the project.

Usage:
    python tools/skills/assign_skills.py --project my-app
    python tools/skills/assign_skills.py --project my-app --goal build-dashboard
    python tools/skills/assign_skills.py --project my-app --dry-run
"""

import argparse
import json
import os
import re
import yaml
from pathlib import Path
from datetime import datetime


def load_registry(framework_root: Path) -> dict:
    """Load the skills registry YAML."""
    registry_path = framework_root / "tools" / "skills" / "skills-registry.yaml"
    if not registry_path.exists():
        print(f"  ✗ Skills registry not found at {registry_path}")
        return {}
    with open(registry_path, 'r') as f:
        return yaml.safe_load(f)


def parse_goal_frontmatter(filepath: Path) -> tuple[dict, str]:
    """Parse YAML frontmatter and body from a goal markdown file."""
    content = filepath.read_text()
    frontmatter = {}
    body = content

    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            try:
                frontmatter = yaml.safe_load(parts[1]) or {}
            except yaml.YAMLError:
                frontmatter = {}
            body = parts[2]

    return frontmatter, body


def write_goal_with_skills(filepath: Path, frontmatter: dict, body: str):
    """Write goal file back with updated frontmatter including skills."""
    fm_str = yaml.dump(frontmatter, default_flow_style=False, sort_keys=False).strip()
    content = f"---\n{fm_str}\n---{body}"
    filepath.write_text(content)


def score_skill(skill_name: str, skill_def: dict, goal_text: str, 
                goal_name: str, sdp_section: dict = None) -> dict:
    """
    Score how relevant a skill is to a goal.
    Returns {score, reasons} where score > 0 means the skill applies.
    """
    score = 0
    reasons = []
    triggers = skill_def.get("triggers", {})

    # 1. Keyword matching (1 point per hit)
    keywords = triggers.get("keywords", [])
    goal_lower = goal_text.lower()
    keyword_hits = []
    for kw in keywords:
        if kw.lower() in goal_lower:
            score += 1
            keyword_hits.append(kw)
    if keyword_hits:
        reasons.append(f"keywords: {', '.join(keyword_hits[:5])}")

    # 2. Goal pattern matching (3 points per match — strong signal)
    patterns = triggers.get("goal_patterns", [])
    for pattern in patterns:
        if re.search(pattern, goal_name.lower()):
            score += 3
            reasons.append(f"goal pattern: {pattern}")
            break  # One pattern match is enough

    # 3. File type matching from SDP section (2 points)
    file_types = triggers.get("file_types", [])
    if sdp_section:
        section_str = json.dumps(sdp_section).lower()
        for ft in file_types:
            if ft.lower() in section_str:
                score += 2
                reasons.append(f"file type: {ft}")
                break

    # 4. Section type wildcard (frontend-design applies to all UI sections)
    section_types = triggers.get("section_types", [])
    if "*" in section_types and goal_name.startswith("build-"):
        score += 2
        reasons.append("applies to all build-* goals")

    # 5. SDP section content analysis
    if sdp_section:
        section_text = json.dumps(sdp_section).lower()
        section_keyword_hits = sum(1 for kw in keywords if kw.lower() in section_text)
        if section_keyword_hits > 2:
            score += section_keyword_hits
            reasons.append(f"{section_keyword_hits} keyword hits in SDP section")

    return {"score": score, "reasons": reasons}


def detect_composite_skills(goal_name: str, goal_text: str, 
                            composites: dict) -> list[dict]:
    """Check if any composite skill sets apply."""
    matches = []
    for comp_name, comp_def in composites.items():
        for pattern in comp_def.get("triggers", []):
            if re.search(pattern, goal_name.lower()) or re.search(pattern, goal_text.lower()):
                matches.append({
                    "name": comp_name,
                    "skills": comp_def["skills"],
                    "description": comp_def.get("description", "")
                })
                break
    return matches


def assign_skills_to_goal(goal_path: Path, registry: dict, 
                          sdp_sections_dir: Path = None, 
                          dry_run: bool = False) -> dict:
    """
    Analyze a single goal file and assign appropriate skills.
    Returns the assignment result.
    """
    goal_name = goal_path.stem
    frontmatter, body = parse_goal_frontmatter(goal_path)
    goal_text = f"{goal_name} {frontmatter.get('title', '')} {body}"

    # Load SDP section if available
    sdp_section = None
    if sdp_sections_dir:
        # Try to find matching SDP section JSON
        section_name = goal_name.replace("build-", "")
        sdp_file = sdp_sections_dir / f"{section_name}.json"
        if sdp_file.exists():
            try:
                with open(sdp_file, 'r') as f:
                    sdp_section = json.load(f)
            except (json.JSONDecodeError, IOError):
                pass

    # Score each skill
    skills_config = registry.get("skills", {})
    scores = {}
    for skill_name, skill_def in skills_config.items():
        result = score_skill(skill_name, skill_def, goal_text, goal_name, sdp_section)
        if result["score"] > 0:
            scores[skill_name] = result

    # Check composite skills
    composites = registry.get("composites", {})
    composite_matches = detect_composite_skills(goal_name, goal_text, composites)

    # Build the final skills list
    # Include skills with score >= 2 (filters out weak single-keyword matches)
    assigned_skills = []
    skill_details = []

    for skill_name, result in sorted(scores.items(), key=lambda x: x[1]["score"], reverse=True):
        if result["score"] >= 2:
            skill_path = skills_config[skill_name].get("path")
            assigned_skills.append({
                "name": skill_name,
                "path": skill_path,
                "score": result["score"],
                "reasons": result["reasons"],
                "has_skill_file": skill_path is not None
            })
            skill_details.append(f"{skill_name} (score: {result['score']})")

    # Add composite skill members that aren't already included
    for comp in composite_matches:
        for comp_skill in comp["skills"]:
            if comp_skill not in [s["name"] for s in assigned_skills]:
                skill_path = skills_config.get(comp_skill, {}).get("path")
                assigned_skills.append({
                    "name": comp_skill,
                    "path": skill_path,
                    "score": 1,
                    "reasons": [f"composite: {comp['name']}"],
                    "has_skill_file": skill_path is not None
                })

    # Write skills to goal frontmatter
    if not dry_run and assigned_skills:
        # Store simplified skill list in frontmatter
        frontmatter["skills"] = [s["name"] for s in assigned_skills]
        frontmatter["skill_paths"] = [s["path"] for s in assigned_skills if s["path"]]
        frontmatter["skills_assigned"] = datetime.now().strftime("%Y-%m-%d")
        write_goal_with_skills(goal_path, frontmatter, body)

    return {
        "goal": goal_name,
        "title": frontmatter.get("title", goal_name),
        "assigned_skills": assigned_skills,
        "composites": composite_matches,
        "total_score": sum(s["score"] for s in assigned_skills),
    }


def generate_skills_map(project_dir: Path, assignments: list) -> str:
    """Generate a project-level skills map document."""
    lines = [
        "# Skills Map\n",
        f"*Auto-generated on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n",
        "This document maps which skills Claude should read before working on each goal.\n",
        "## How to Use\n",
        "Before starting any goal, Claude should:\n",
        "1. Read this file to see which skills are assigned",
        "2. Use the `view` tool to read each listed SKILL.md file",
        "3. Follow the skill's best practices while implementing the goal\n",
        "## Goal → Skills Matrix\n",
        "| Goal | Skills | Skill Files to Read |",
        "|------|--------|---------------------|",
    ]

    for assignment in assignments:
        goal = assignment["goal"]
        skills = ", ".join(s["name"] for s in assignment["assigned_skills"])
        skill_files = ", ".join(
            f'`{s["path"]}`' for s in assignment["assigned_skills"] if s["path"]
        )
        if not skill_files:
            skill_files = "*(no skill files — use built-in knowledge)*"
        lines.append(f"| {goal} | {skills} | {skill_files} |")

    lines.append("")

    # Detailed breakdown per goal
    lines.append("\n## Detailed Assignments\n")
    for assignment in assignments:
        goal = assignment["goal"]
        title = assignment["title"]
        lines.append(f"### {goal}")
        lines.append(f"**{title}**\n")

        if assignment["assigned_skills"]:
            for skill in assignment["assigned_skills"]:
                has_file = "📄" if skill["has_skill_file"] else "🧠"
                reasons = "; ".join(skill["reasons"])
                path_note = f" → `{skill['path']}`" if skill["path"] else " → *use built-in knowledge*"
                lines.append(f"- {has_file} **{skill['name']}** (relevance: {skill['score']}){path_note}")
                lines.append(f"  - Why: {reasons}")
        else:
            lines.append("- *No specific skills assigned — use general knowledge*")

        if assignment["composites"]:
            for comp in assignment["composites"]:
                lines.append(f"- 🔗 Composite: **{comp['name']}** — {comp['description']}")

        lines.append("")

    # Summary section
    lines.append("\n## Skill Usage Summary\n")
    skill_counts = {}
    for assignment in assignments:
        for skill in assignment["assigned_skills"]:
            name = skill["name"]
            skill_counts[name] = skill_counts.get(name, 0) + 1

    lines.append("| Skill | Used In # Goals | Has Skill File |")
    lines.append("|-------|-----------------|----------------|")
    for skill_name, count in sorted(skill_counts.items(), key=lambda x: x[1], reverse=True):
        has_file = "✅" if any(
            s["path"] for a in assignments for s in a["assigned_skills"] if s["name"] == skill_name
        ) else "❌"
        lines.append(f"| {skill_name} | {count} | {has_file} |")

    lines.append(f"\n\n---\n*Generated by skills assigner — re-run `assign_skills.py` to update*\n")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Assign skills to project goals")
    parser.add_argument("--project", required=True, help="Project name")
    parser.add_argument("--goal", help="Specific goal to analyze (default: all goals)")
    parser.add_argument("--framework-root", default=".", help="Framework root directory")
    parser.add_argument("--dry-run", action="store_true", help="Show assignments without writing")
    parser.add_argument("--verbose", action="store_true", help="Show detailed scoring")
    args = parser.parse_args()

    framework_root = Path(args.framework_root).resolve()
    project_dir = framework_root / "projects" / args.project
    goals_dir = project_dir / "goals"
    context_dir = project_dir / "context"
    sdp_sections_dir = context_dir / "sdp-source" / "sections"

    print(f"\n{'='*60}")
    print(f"  Skills Assigner")
    print(f"{'='*60}\n")

    # Load registry
    print("📚 Loading skills registry...")
    registry = load_registry(framework_root)
    if not registry:
        print("  ✗ Failed to load registry. Exiting.")
        return

    skills_count = len(registry.get("skills", {}))
    composites_count = len(registry.get("composites", {}))
    print(f"  ✓ {skills_count} skills + {composites_count} composites loaded\n")

    # Check project exists
    if not goals_dir.exists():
        print(f"  ✗ Goals directory not found: {goals_dir}")
        return

    # Find goals to process
    if args.goal:
        goal_files = [goals_dir / f"{args.goal}.md"]
        if not goal_files[0].exists():
            goal_files = [goals_dir / f"build-{args.goal}.md"]
        if not goal_files[0].exists():
            print(f"  ✗ Goal not found: {args.goal}")
            return
    else:
        goal_files = sorted(goals_dir.glob("*.md"))

    if not goal_files:
        print(f"  ✗ No goal files found in {goals_dir}")
        return

    print(f"🎯 Analyzing {len(goal_files)} goals...\n")

    # Check for SDP sections
    has_sdp = sdp_sections_dir.exists() and any(sdp_sections_dir.glob("*.json"))
    if has_sdp:
        sdp_count = len(list(sdp_sections_dir.glob("*.json")))
        print(f"📦 SDP sections available: {sdp_count} files (will use for deeper analysis)\n")
    else:
        print(f"📦 No SDP sections found (using goal text only for analysis)\n")
        sdp_sections_dir = None

    # Process each goal
    assignments = []
    for goal_path in goal_files:
        result = assign_skills_to_goal(
            goal_path, registry, sdp_sections_dir, dry_run=args.dry_run
        )
        assignments.append(result)

        # Display result
        goal_name = result["goal"]
        skill_names = [s["name"] for s in result["assigned_skills"]]
        skill_files = [s["path"] for s in result["assigned_skills"] if s["path"]]

        if skill_names:
            status = "🔧" if not args.dry_run else "👁"
            print(f"  {status} {goal_name}")
            print(f"     Skills: {', '.join(skill_names)}")
            if skill_files:
                print(f"     Read:   {', '.join(skill_files)}")
            if args.verbose:
                for skill in result["assigned_skills"]:
                    print(f"       → {skill['name']}: score={skill['score']}, {'; '.join(skill['reasons'])}")
        else:
            print(f"  ⚪ {goal_name} — no specific skills needed")

    # Generate skills map
    if not args.dry_run:
        print(f"\n📋 Generating skills map...")
        skills_map_content = generate_skills_map(project_dir, assignments)
        skills_map_path = context_dir / "skills-map.md"
        skills_map_path.write_text(skills_map_content)
        print(f"  ✓ Written to {skills_map_path}")

    # Summary
    print(f"\n{'='*60}")
    total_assignments = sum(len(a["assigned_skills"]) for a in assignments)
    goals_with_skills = sum(1 for a in assignments if a["assigned_skills"])
    print(f"  ✅ {total_assignments} skill assignments across {goals_with_skills}/{len(assignments)} goals")

    if args.dry_run:
        print(f"  ℹ  Dry run — no files were modified")
    else:
        print(f"  📄 Goal frontmatter updated with skill assignments")
        print(f"  📋 Skills map written to context/skills-map.md")

    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
