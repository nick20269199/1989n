# Rules

## Structure

```
rules/
├── common/        # Universal principles (always loaded)
├── python/        # Python-specific (extend with other languages as needed)
├── agents/        # Agent architecture constraints (U1-U4, from philosophy 500 books)
├── security/      # Security & alignment (U1/U5/U7, from philosophy 500 books)
└── performance/   # Cognitive performance (U2/U3/U6, from philosophy 500 books)
```

- **common/** contains language-agnostic coding standards, security checklists, and workflow.
- **python/** extends common with Python tools and idioms.

## Installation

```bash
cp -r rules/common ~/.claude/rules/common
cp -r rules/python ~/.claude/rules/python  # adjust to project language
```

## Rule Priority

Language-specific rules override common rules where idioms differ.

## Rules vs Skills

- **Rules** define standards and checklists (e.g., "80% test coverage", "no hardcoded secrets")
- **Skills** (`skills/` directory) provide deep reference material for specific tasks
