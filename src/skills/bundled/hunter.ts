import { registerBundledSkill } from '../bundledSkills.js'

export function registerHunterSkill(): void {
  registerBundledSkill({
    name: 'hunter',
    description:
      'Review and analyze code artifacts, PRs, or commits for quality and issues',
    userInvocable: true,
    isEnabled: () => true,
    async getPromptForCommand(args) {
      const target = args ? args.trim() : 'the specified artifact'
      const prompt = `# Hunter: Artifact Review

Review ${target} for bugs, style issues, and correctness.

## Review Checklist

1. **Correctness** — Does the code do what it claims? Are there logic errors or off-by-one bugs?
2. **Style** — Does the code follow the project's style conventions (naming, formatting, structure)?
3. **Error handling** — Are errors caught and handled appropriately?
4. **Edge cases** — Are boundary conditions and unexpected inputs handled?
5. **Security** — Are there injection risks, unvalidated inputs, or unsafe operations?
6. **Performance** — Are there obvious inefficiencies (N+1 queries, unnecessary allocations)?
7. **Tests** — Are the changes adequately tested? Are test cases comprehensive?
8. **Documentation** — Are public APIs and non-obvious logic documented?

## Output Format

Provide a structured review with:
- **Summary**: One paragraph overall assessment
- **Issues**: Numbered list of specific problems (severity: critical / major / minor / nit)
- **Suggestions**: Optional improvements that aren't bugs
- **Verdict**: LGTM / Request Changes / Needs Discussion
`

      return [{ type: 'text', text: prompt }]
    },
  })
}
