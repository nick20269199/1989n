---
name: skill-creator
description: Create new skills, modify and improve existing skills. Use when users want to create a skill from scratch, edit, or optimize an existing skill.
---

# Skill Creator

Help the user create a new skill by guiding them through these steps:

1. **Define the skill**: Ask what the skill should do, when it should trigger, and what tools it needs.
2. **Create the folder structure**: Create a folder in `~/.claude/skills/` with the skill name (kebab-case).
3. **Write SKILL.md**: Create the SKILL.md file with proper YAML frontmatter (name, description) and markdown instructions.
4. **Optional files**: Create scripts/, references/, or assets/ subdirectories if needed.

## SKILL.md Format

```markdown
---
name: your-skill-name
description: What it does. Use when [trigger conditions].
---

# Your Skill Name

## Instructions

### Step 1: [First Major Step]
Clear explanation of what happens.

### Step 2: [Next Step]
...
```

## Rules
- Folder name must be kebab-case (e.g., `my-cool-skill`)
- File must be exactly `SKILL.md` (case-sensitive)
- Description must include what it does AND when to use it
- No XML angle brackets in frontmatter
- Keep SKILL.md focused on core instructions; put detailed docs in references/

## 易错点（Gotchas）

- **description是给模型看的不是给人看的**: description字段必须精准回答"什么情况下触发这个skill"，写成工作总结没用。参考现有skill的TRIGGER/DO NOT TRIGGER格式
- **别教AI显而易见的内容**: 不需要教它"什么是函数"、"怎么写CSS"。要告诉它**打破默认思维**的信息，例如"不要用Inter字体"、"不要用紫色渐变"
- **Gotchas是skill最有价值的部分**: 把AI反复在同一地方翻车的错误模式记下来，随着使用持续补充。官方建议：最初版本就是几行指令+一个易错点列表，用久了自然丰富
- **渐进式披露**: 主文件不要塞所有内容。详细API文档放 `references/api.md`，模板放 `templates/`，主文件只放指针让AI按需读取
- **别写死指令**: 每次场景不同，只需给核心任务信息，让模型根据具体情况自行判断
- **skill是文件夹不是单文件**: 可以包含scripts/、data assets、config files、dynamic hooks
- **name必须kebab-case**: `my-cool-skill` 不是 `My Cool Skill`
- **文件必须叫SKILL.md**: 大小写敏感，不是skill.md或Skill.md
