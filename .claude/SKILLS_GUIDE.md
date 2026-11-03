# Claude Code Skills for supportKB

This project includes **three custom Claude Code skills** to assist with development. When working with Claude Code, you can invoke these skills to get context-specific guidance and commands.

## Available Skills

### 1. `/supportkb-context`
**Comprehensive project context and architecture guide**

Use this when:
- You're new to the project and need to understand the architecture
- You need to know the directory structure and key files
- You want common development commands
- You're setting up the development environment
- You need to understand the LangGraph workflow

**Quick start**: `/supportkb-context`

### 2. `/supportkb-testing`
**Testing, validation, and quality assurance**

Use this when:
- You need to run tests or check code quality
- You want to validate workflows
- You're checking for production readiness
- You need to set up LangSmith evaluations
- You're debugging a failing test

**Quick start**: `/supportkb-testing`

### 3. `/supportkb-integrations`
**Integration configuration and troubleshooting**

Use this when:
- You're setting up external APIs (Vehicle API, Ticket System, etc.)
- You need to configure environment variables
- You're troubleshooting integration issues
- You want to understand adapter patterns
- You're testing API connectivity

**Quick start**: `/supportkb-integrations`

## How to Use Skills in Claude Code

### In the CLI
```bash
# List all available skills
/help

# Invoke a skill by name
/supportkb-context
/supportkb-testing
/supportkb-integrations
```

### In the Web App (claude.ai/code)
Type the skill name with a leading slash in the chat prompt:

```
/supportkb-testing

I need to run the tests for the fault classifier.
```

### In IDE Extensions (VS Code, JetBrains)
Skills are available through the Claude Code IDE extension chat interface. Type `/` to see available skills.

## Sharing These Skills with Your Team

These skill definitions are stored in `.claude/skills/` and are committed to the repository. When team members clone the project, they'll automatically have access to these skills through their Claude Code installation.

### For New Team Members
1. Clone the repository
2. Open Claude Code
3. Use any of the three skills with `/skill-name`

### Updating Skills
If you modify a skill definition (in `.claude/skills/*/SKILL.md`):
1. Edit the SKILL.md file
2. Commit the changes
3. Team members will pick up the updated skill on next sync

## Project Documentation

These skills complement the main project documentation:
- **CLAUDE.md**: Developer guide checked into the repo
- **README.md**: Project setup and overview
- **docs/postgres_schema.sql**: PostgreSQL schema reference
- **docs/graph.md**: LangGraph workflow diagram

## Need Help?

If a skill doesn't answer your question:
1. Check the relevant project documentation (CLAUDE.md, README.md)
2. Refer to the source code (well-organized by responsibility)
3. Ask Claude Code with more context: `I'm working on [task], help me with [specific question]`

---

Happy coding! 🚀
