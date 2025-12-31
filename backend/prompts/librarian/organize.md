# Librarian Organization Task Prompt

## Task Assignment

The Oracle has delegated the following organization task to you:

**Task Description**: {{ task }}

{% if folder %}
**Target Folder**: {{ folder }}
{% endif %}

{% if files %}
**Specific Files**:
{% for file in files %}
- {{ file }}
{% endfor %}
{% endif %}

## Execution Guidelines

### Phase 1: Discovery

Before making any changes, understand the current state:

1. Use `vault_list` to see the current folder structure
2. Use `vault_read` to examine the content of relevant notes
3. Use `vault_search` to find related content that might be affected
4. If organizing around code, use `search_code` to understand implementation context

### Phase 2: Planning

Determine your organization strategy:

1. Identify logical groupings based on content similarity
2. Check for existing wikilinks that connect notes
3. Plan file moves to minimize link breakage
4. Decide if new index pages are needed

### Phase 3: Execution

Make changes incrementally:

1. Create any new folders by writing a placeholder or index file
2. Move files using `vault_move` (handles wikilink updates)
3. Create index pages using `vault_create_index`
4. Update any notes that need new wikilinks

### Phase 4: Verification

Confirm the reorganization is complete:

1. Use `vault_list` to verify new structure
2. Use `vault_search` to check for broken links
3. Read key files to ensure wikilinks resolve correctly

## Common Organization Patterns

### Folder-per-Topic
```
topic-name/
  index.md          <- Overview with links to subtopics
  subtopic-a.md
  subtopic-b.md
```

### Chronological Organization
```
decisions/
  2025-01-auth-design.md
  2025-01-api-contract.md
  index.md          <- Links sorted by date
```

### Component-Based
```
components/
  auth/
    overview.md
    jwt-handler.md
  api/
    routes.md
    middleware.md
```

## Edge Cases

### Conflicting Names
If two notes would have the same name in the target folder:
1. Report the conflict
2. Do NOT overwrite
3. Suggest rename options

### Circular Links
If organization would create circular wikilink dependencies:
1. Proceed with the move
2. Note the circular reference in your report

### External References
If notes link to files outside the vault:
1. Keep those links unchanged
2. Note them in your report for the Oracle

## Quality Checklist

Before reporting completion, verify:

- [ ] All requested files have been addressed
- [ ] Index pages link to all relevant notes
- [ ] No orphaned notes (notes with no incoming links) were created
- [ ] Folder structure follows project conventions
- [ ] Wikilinks use consistent naming (title-based, not path-based)

## Report Template

```markdown
## Organization Complete

### Summary
[One-sentence summary of what was organized]

### Changes Made
1. **Moved**: `old/path/note.md` -> `new/path/note.md`
2. **Created**: `folder/index.md` - Index page for [topic]
3. **Updated**: `related/note.md` - Added wikilink to new content

### Structure After
```
folder/
  index.md
  note-a.md
  note-b.md
```

### Wikilink Updates
- `[[Old Name]]` references updated to `[[New Name]]` in X files

### Issues
- [Any problems encountered]

### Recommendations
- [Suggestions for the Oracle or user]
```
