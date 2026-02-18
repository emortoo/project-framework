#!/usr/bin/env python3
"""
SDP-to-Framework Bridge

Converts a Software Design Package (SDP) from Software Design OS
into the Project Framework's context and goals structure.

Usage:
    python tools/sdp-bridge/sdp_to_context.py --sdp ./exports/my-app.sdp --project my-app
    python tools/sdp-bridge/sdp_to_context.py --sdp ./my-app.zip --project my-app
"""

import argparse
import json
import os
import shutil
import zipfile
import re
from pathlib import Path
from datetime import datetime


def kebab_case(text: str) -> str:
    """Convert text to kebab-case."""
    text = re.sub(r'[^\w\s-]', '', text.lower())
    return re.sub(r'[\s_]+', '-', text).strip('-')


def read_json(path: Path) -> dict | None:
    """Safely read a JSON file."""
    if path.exists():
        try:
            with open(path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"  ⚠ Warning: Could not read {path}: {e}")
    return None


def read_text(path: Path) -> str | None:
    """Safely read a text file."""
    if path.exists():
        try:
            with open(path, 'r') as f:
                return f.read()
        except IOError:
            pass
    return None


def detect_stack(stack_data: dict) -> str:
    """Map SDP stack info to a framework stack name."""
    if not stack_data:
        return "orbit"  # default

    deps = stack_data.get("dependencies", {})
    framework = stack_data.get("framework", "").lower()
    
    # Check for Next.js
    if "next" in framework or "next" in str(deps):
        return "nextjs"
    
    # Check for Python/FastAPI
    if "fastapi" in framework or "flask" in framework or "django" in framework:
        return "python-fastapi"
    
    # Check for static
    if "static" in framework or (not deps and not framework):
        return "static"
    
    # Default to orbit (React + Vite)
    return "orbit"


def generate_product_context(sdp_path: Path) -> str:
    """Generate product.md from SDP product definition."""
    definition = read_json(sdp_path / "product" / "definition.json")
    definition_md = read_text(sdp_path / "product" / "definition.md")
    
    lines = ["# Product Context\n"]
    
    if definition:
        lines.append("## Overview\n")
        if "name" in definition:
            lines.append(f"**Product:** {definition['name']}\n")
        if "description" in definition:
            lines.append(f"{definition['description']}\n")
        
        if "problems" in definition:
            lines.append("\n## Problems & Solutions\n")
            for item in definition["problems"]:
                problem = item.get("problem", item) if isinstance(item, dict) else item
                solution = item.get("solution", "") if isinstance(item, dict) else ""
                lines.append(f"**Problem:** {problem}")
                if solution:
                    lines.append(f"**Solution:** {solution}\n")
        
        if "features" in definition:
            lines.append("\n## Key Features\n")
            for feat in definition["features"]:
                if isinstance(feat, dict):
                    name = feat.get("name", "")
                    desc = feat.get("description", "")
                    lines.append(f"- **{name}**: {desc}")
                else:
                    lines.append(f"- {feat}")
        
        if "personas" in definition or "users" in definition:
            lines.append("\n## Target Users\n")
            users = definition.get("personas", definition.get("users", []))
            for user in users:
                if isinstance(user, dict):
                    lines.append(f"- **{user.get('name', 'User')}**: {user.get('description', '')}")
                else:
                    lines.append(f"- {user}")
    
    if definition_md:
        lines.append(f"\n---\n\n## Full Product Definition\n\n{definition_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_datamodel_context(sdp_path: Path) -> str:
    """Generate data-model.md from SDP data model."""
    entities = read_json(sdp_path / "data-model" / "entities.json")
    relationships = read_json(sdp_path / "data-model" / "relationships.json")
    datamodel_md = read_text(sdp_path / "data-model" / "data-model.md")
    
    lines = ["# Data Model\n"]
    
    if entities:
        lines.append("## Entities\n")
        entity_list = entities if isinstance(entities, list) else entities.get("entities", [])
        for entity in entity_list:
            if isinstance(entity, dict):
                name = entity.get("name", "Unknown")
                desc = entity.get("description", "")
                lines.append(f"### {name}\n")
                if desc:
                    lines.append(f"{desc}\n")
                
                fields = entity.get("fields", entity.get("attributes", []))
                if fields:
                    lines.append("| Field | Type | Required | Description |")
                    lines.append("|-------|------|----------|-------------|")
                    for field in fields:
                        if isinstance(field, dict):
                            fname = field.get("name", "")
                            ftype = field.get("type", "")
                            freq = "Yes" if field.get("required", False) else "No"
                            fdesc = field.get("description", "")
                            lines.append(f"| {fname} | {ftype} | {freq} | {fdesc} |")
                    lines.append("")
        
        # Raw JSON reference
        lines.append("\n## Raw Entity Schema\n")
        lines.append("```json")
        lines.append(json.dumps(entities, indent=2))
        lines.append("```\n")
    
    if relationships:
        lines.append("\n## Relationships\n")
        lines.append("```json")
        lines.append(json.dumps(relationships, indent=2))
        lines.append("```\n")
    
    if datamodel_md:
        lines.append(f"\n---\n\n## Full Data Model Documentation\n\n{datamodel_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_database_context(sdp_path: Path) -> str:
    """Generate database.md from SDP database design."""
    schema = read_json(sdp_path / "database" / "schema.json")
    schema_sql = read_text(sdp_path / "database" / "schema.sql")
    database_md = read_text(sdp_path / "database" / "database.md")
    
    lines = ["# Database Design\n"]
    
    if schema:
        engine = schema.get("engine", "postgresql")
        lines.append(f"**Engine:** {engine}\n")
        
        lines.append("\n## Schema Configuration\n")
        lines.append("```json")
        lines.append(json.dumps(schema, indent=2))
        lines.append("```\n")
    
    if schema_sql:
        lines.append("\n## SQL Schema\n")
        lines.append("```sql")
        lines.append(schema_sql)
        lines.append("```\n")
    
    if database_md:
        lines.append(f"\n---\n\n{database_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_api_context(sdp_path: Path) -> str:
    """Generate api.md from SDP API design."""
    endpoints = read_json(sdp_path / "api" / "endpoints.json")
    api_md = read_text(sdp_path / "api" / "api-spec.md")
    
    lines = ["# API Design\n"]
    
    if endpoints:
        lines.append("## Endpoints\n")
        
        endpoint_list = endpoints if isinstance(endpoints, list) else endpoints.get("endpoints", [])
        if endpoint_list:
            lines.append("| Method | Path | Description |")
            lines.append("|--------|------|-------------|")
            for ep in endpoint_list:
                if isinstance(ep, dict):
                    method = ep.get("method", "GET")
                    path = ep.get("path", ep.get("endpoint", ""))
                    desc = ep.get("description", "")
                    lines.append(f"| {method} | `{path}` | {desc} |")
            lines.append("")
        
        # Auth strategy
        auth = endpoints.get("auth", endpoints.get("authentication", {}))
        if auth:
            lines.append(f"\n## Authentication\n")
            lines.append("```json")
            lines.append(json.dumps(auth, indent=2))
            lines.append("```\n")
        
        lines.append("\n## Full API Spec\n")
        lines.append("```json")
        lines.append(json.dumps(endpoints, indent=2))
        lines.append("```\n")
    
    if api_md:
        lines.append(f"\n---\n\n{api_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_stack_context(sdp_path: Path) -> str:
    """Generate stack.md from SDP stack selection."""
    dependencies = read_json(sdp_path / "stack" / "dependencies.json")
    structure = read_json(sdp_path / "stack" / "structure.json")
    stack_md = read_text(sdp_path / "stack" / "stack.md")
    
    lines = ["# Programming Stack\n"]
    
    if dependencies:
        lines.append("## Dependencies\n")
        lines.append("```json")
        lines.append(json.dumps(dependencies, indent=2))
        lines.append("```\n")
    
    if structure:
        lines.append("\n## Project Structure\n")
        lines.append("```json")
        lines.append(json.dumps(structure, indent=2))
        lines.append("```\n")
    
    if stack_md:
        lines.append(f"\n---\n\n{stack_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_design_context(sdp_path: Path) -> str:
    """Generate design-system.md from SDP design tokens."""
    tokens = read_json(sdp_path / "design" / "tokens.json")
    design_md = read_text(sdp_path / "design" / "design-system.md")
    
    lines = ["# Design System\n"]
    
    if tokens:
        # Colors
        colors = tokens.get("colors", {})
        if colors:
            lines.append("## Colors\n")
            for category, values in colors.items():
                if isinstance(values, dict):
                    lines.append(f"### {category.title()}")
                    for shade, hex_val in values.items():
                        lines.append(f"- `{shade}`: {hex_val}")
                else:
                    lines.append(f"- **{category}**: {values}")
            lines.append("")
        
        # Typography
        typography = tokens.get("typography", {})
        if typography:
            lines.append("\n## Typography\n")
            for key, val in typography.items():
                lines.append(f"- **{key}**: {val}")
            lines.append("")
        
        # Spacing
        spacing = tokens.get("spacing", {})
        if spacing:
            lines.append("\n## Spacing\n")
            lines.append("```json")
            lines.append(json.dumps(spacing, indent=2))
            lines.append("```\n")
        
        # Full token reference
        lines.append("\n## Full Design Tokens\n")
        lines.append("```json")
        lines.append(json.dumps(tokens, indent=2))
        lines.append("```\n")
    
    if design_md:
        lines.append(f"\n---\n\n{design_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_infrastructure_context(sdp_path: Path) -> str:
    """Generate infrastructure.md from SDP infrastructure config."""
    deployment = read_json(sdp_path / "infrastructure" / "deployment.json")
    infra_md = read_text(sdp_path / "infrastructure" / "infrastructure.md")
    
    lines = ["# Infrastructure & Deployment\n"]
    
    if deployment:
        lines.append("## Deployment Configuration\n")
        lines.append("```json")
        lines.append(json.dumps(deployment, indent=2))
        lines.append("```\n")
    
    if infra_md:
        lines.append(f"\n---\n\n{infra_md}")
    
    lines.append(f"\n\n---\n*Imported from SDP on {datetime.now().strftime('%Y-%m-%d %H:%M')}*\n")
    return "\n".join(lines)


def generate_goal_from_section(section_name: str, section_data: dict, section_md: str = None) -> str:
    """Generate a goal file from an SDP section specification."""
    title = section_data.get("name", section_name.replace("-", " ").title())
    description = section_data.get("description", f"Build the {title} section of the application.")
    
    lines = [
        "---",
        f'title: "Build {title}"',
        f"status: not-started",
        f"priority: medium",
        f"created: {datetime.now().strftime('%Y-%m-%d')}",
        f"source: sdp-import",
        "---\n",
        f"# Build {title}\n",
        f"{description}\n",
    ]
    
    # Components as acceptance criteria
    components = section_data.get("components", section_data.get("componentTree", []))
    if components:
        lines.append("## Acceptance Criteria\n")
        if isinstance(components, list):
            for comp in components:
                if isinstance(comp, dict):
                    comp_name = comp.get("name", comp.get("component", ""))
                    comp_desc = comp.get("description", comp.get("purpose", ""))
                    lines.append(f"- [ ] {comp_name} is implemented and functional" + (f" — {comp_desc}" if comp_desc else ""))
                else:
                    lines.append(f"- [ ] {comp} is implemented and functional")
        elif isinstance(components, dict):
            for comp_name, comp_detail in components.items():
                desc = comp_detail if isinstance(comp_detail, str) else ""
                lines.append(f"- [ ] {comp_name} is implemented and functional" + (f" — {desc}" if desc else ""))
        lines.append("")
    
    # Data requirements
    data_reqs = section_data.get("dataRequirements", section_data.get("entities", []))
    if data_reqs:
        lines.append("## Data Requirements\n")
        lines.append("Reference: `context/data-model.md`\n")
        if isinstance(data_reqs, list):
            for req in data_reqs:
                lines.append(f"- {req}")
        lines.append("")
    
    # Interactions
    interactions = section_data.get("interactions", section_data.get("behaviors", []))
    if interactions:
        lines.append("## Interactions & Behaviors\n")
        if isinstance(interactions, list):
            for interaction in interactions:
                if isinstance(interaction, dict):
                    lines.append(f"- **{interaction.get('trigger', 'Action')}**: {interaction.get('behavior', interaction.get('description', ''))}")
                else:
                    lines.append(f"- {interaction}")
        lines.append("")
    
    # Raw section spec reference
    lines.append("## SDP Section Reference\n")
    lines.append("Full specification available at: `context/sdp-source/sections/`\n")
    lines.append("```json")
    lines.append(json.dumps(section_data, indent=2))
    lines.append("```\n")
    
    if section_md:
        lines.append(f"\n---\n\n## Full Section Spec\n\n{section_md}")
    
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Import SDP into Project Framework")
    parser.add_argument("--sdp", required=True, help="Path to SDP folder or .zip")
    parser.add_argument("--project", required=True, help="Target project name in the framework")
    parser.add_argument("--framework-root", default=".", help="Root of the project-framework (default: current dir)")
    args = parser.parse_args()
    
    framework_root = Path(args.framework_root).resolve()
    project_dir = framework_root / "projects" / args.project
    sdp_path = Path(args.sdp).resolve()
    
    print(f"\n{'='*60}")
    print(f"  SDP → Project Framework Bridge")
    print(f"{'='*60}\n")
    
    # Handle zip extraction
    if sdp_path.suffix == ".zip":
        print(f"📦 Extracting SDP from {sdp_path.name}...")
        extract_dir = Path("/tmp/sdp-import")
        if extract_dir.exists():
            shutil.rmtree(extract_dir)
        with zipfile.ZipFile(sdp_path, 'r') as zf:
            zf.extractall(extract_dir)
        # Find the actual SDP root (might be nested)
        if (extract_dir / "sdp.json").exists():
            sdp_path = extract_dir
        else:
            subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
            if subdirs and (subdirs[0] / "sdp.json").exists():
                sdp_path = subdirs[0]
            else:
                sdp_path = extract_dir
        print(f"  ✓ Extracted to {sdp_path}\n")
    
    # Validate SDP
    print("🔍 Validating SDP structure...")
    manifest = read_json(sdp_path / "sdp.json")
    
    expected_files = {
        "product/definition.json": "Product Definition",
        "data-model/entities.json": "Data Model (Entities)",
        "data-model/relationships.json": "Data Model (Relationships)",
        "database/schema.json": "Database Schema",
        "api/endpoints.json": "API Design",
        "stack/dependencies.json": "Stack Dependencies",
        "design/tokens.json": "Design Tokens",
        "infrastructure/deployment.json": "Infrastructure",
    }
    
    found = []
    missing = []
    for filepath, label in expected_files.items():
        if (sdp_path / filepath).exists():
            found.append(label)
            print(f"  ✓ {label}")
        else:
            missing.append(label)
            print(f"  ⚠ {label} — not found")
    
    # Check for sections
    sections_dir = sdp_path / "sections"
    section_files = []
    if sections_dir.exists():
        section_files = sorted(sections_dir.glob("*.json"))
        print(f"  ✓ Sections: {len(section_files)} found")
    else:
        print(f"  ⚠ Sections directory — not found")
    
    print(f"\n  Found: {len(found)}/{len(expected_files)} core files + {len(section_files)} sections\n")
    
    # Check project exists
    if not project_dir.exists():
        print(f"⚠ Project '{args.project}' not found at {project_dir}")
        print(f"  Run init first: python tools/init/init_project.py --name {args.project} --stack <stack>")
        print(f"  Or create the directory structure manually.\n")
        
        # Create minimal structure
        print(f"📁 Creating minimal project structure...")
        context_dir = project_dir / "context"
        goals_dir = project_dir / "goals"
        context_dir.mkdir(parents=True, exist_ok=True)
        goals_dir.mkdir(parents=True, exist_ok=True)
        print(f"  ✓ Created {project_dir}\n")
    
    context_dir = project_dir / "context"
    goals_dir = project_dir / "goals"
    context_dir.mkdir(parents=True, exist_ok=True)
    goals_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate context files
    print("📝 Generating context files...\n")
    
    context_generators = [
        ("product.md", generate_product_context),
        ("data-model.md", generate_datamodel_context),
        ("database.md", generate_database_context),
        ("api.md", generate_api_context),
        ("stack.md", generate_stack_context),
        ("design-system.md", generate_design_context),
        ("infrastructure.md", generate_infrastructure_context),
    ]
    
    for filename, generator in context_generators:
        try:
            content = generator(sdp_path)
            filepath = context_dir / filename
            with open(filepath, 'w') as f:
                f.write(content)
            print(f"  ✓ {filename}")
        except Exception as e:
            print(f"  ✗ {filename} — Error: {e}")
    
    # Generate goals from sections
    if section_files:
        print(f"\n🎯 Generating goals from {len(section_files)} sections...\n")
        for section_file in section_files:
            section_name = section_file.stem
            section_data = read_json(section_file)
            section_md = read_text(sdp_path / "sections" / f"{section_name}.md")
            
            if section_data:
                try:
                    goal_content = generate_goal_from_section(section_name, section_data, section_md)
                    goal_filename = f"build-{kebab_case(section_name)}.md"
                    goal_path = goals_dir / goal_filename
                    with open(goal_path, 'w') as f:
                        f.write(goal_content)
                    print(f"  ✓ {goal_filename}")
                except Exception as e:
                    print(f"  ✗ {section_name} — Error: {e}")
    
    # Copy original SDP as reference
    print(f"\n📋 Storing original SDP as reference...")
    sdp_ref_dir = context_dir / "sdp-source"
    if sdp_ref_dir.exists():
        shutil.rmtree(sdp_ref_dir)
    shutil.copytree(sdp_path, sdp_ref_dir, dirs_exist_ok=True)
    print(f"  ✓ Copied to {sdp_ref_dir}\n")
    
    # Summary
    print(f"{'='*60}")
    print(f"  ✅ SDP Import Complete!")
    print(f"{'='*60}\n")
    
    product_def = read_json(sdp_path / "product" / "definition.json")
    product_name = product_def.get("name", args.project) if product_def else args.project
    
    stack_data = read_json(sdp_path / "stack" / "dependencies.json")
    detected_stack = detect_stack(stack_data)
    
    print(f"  Product:  {product_name}")
    print(f"  Project:  {args.project}")
    print(f"  Stack:    {detected_stack}")
    print(f"  Context:  {len(context_generators)} files generated")
    print(f"  Goals:    {len(section_files)} section goals created")
    print(f"  SDP Ref:  {sdp_ref_dir}\n")
    print(f"  Next steps:")
    print(f"    1. Review context files: projects/{args.project}/context/")
    print(f"    2. Review goals: projects/{args.project}/goals/")
    print(f"    3. Start building: /goals\n")


if __name__ == "__main__":
    main()
