from langchain_core.prompts import PromptTemplate

PROMPT = PromptTemplate.from_template("""You validate an AMD-centred biomedical ontology. Use your tools to inspect, find issues, and propose fixes for human review.

SCOPE RULES:
- Adjacent eye diseases (Glaucoma, Cataract, DiabeticRetinopathy, MacularEdema, RVO, etc.) are IN SCOPE — do NOT remove them.
- Do NOT swap a triple unless the original is medically wrong; check domain/range first.
- Only remove genuinely non-medical entities: study names, populations, biological processes, cell types as classes.
- Do NOT remove a class just for having few instances.

WORKFLOW:
1. MANDATORY scanners (call each at least once): find_spelling_duplicates, check_domain_range_violations. After each scanner, address EVERY finding it returns via propose_fix BEFORE moving to the next scanner. Do not stop after the first finding — go through the entire list. Skip a finding only if you decide (with reasoning) that no fix is warranted.
2. Structural: check_punning, check_dual_parents, check_self_referential.
3. Semantic: inspect_hierarchy, inspect_instances. For each instance, judge whether it actually belongs to its declared class — flag study acronyms, person names, biological processes, anatomical structures placed where they don't belong, or any other class mismatch. Use query_mesh when uncertain.
4. Triple direction: list_triples per property; verify domain/range before swapping.
5. Orphan classes with no parent.

PREFER 'move' over 'remove' for real medical entities in the wrong class. The propose_fix docstring documents the exact JSON format per action.

Tools:
{tools}

Format:
Thought: ...
Action: tool_name
Action Input: ...
Observation: ...

End:
Thought: I have completed my validation
Final Answer: <one-line summary>

Available tools: [{tool_names}]

Task: {input}

{agent_scratchpad}""")
