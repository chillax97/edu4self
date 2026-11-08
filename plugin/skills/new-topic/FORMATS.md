# Topic files

The files every topic folder keeps, besides lessons and probes (those have their own skills,
`write-lesson` and `write-probe`). Adapted from the `teach`
skill by Matt Pocock (MIT, notice at the end).

| file | what it holds | written when |
|---|---|---|
| `MISSION.md` | why the learner wants this | the topic starts; the goal moves |
| `RESOURCES.md` | the trusted sources lessons draw from | the topic starts; a gap is found |
| `GLOSSARY.md` | terms the learner has proven they can use | a term is used right without notes |
| `learning-records/NNNN-<slug>.md` | decision-grade facts about the learner | a grade shows something non-obvious |
| `NOTES.md` | how the learner likes to be taught, working notes | they say so, or you notice |
| `Dashboard.md` | one line per event, newest last | every grading |
| `reference/NNNN-<slug>.html` | cheat sheets: the compressed lesson | with each lesson that has something to keep |
| `assets/` | `lesson.css`, `quiz.js` and other shared parts | the first lesson; anything a second lesson would reuse |

## MISSION.md

```md
# Mission: {Topic}

## Why
{1-3 sentences: the real outcome. "Order dinner and rent a flat in Madrid by June", not "learn Spanish".}

## Success looks like
- {something observable the learner will be able to do}

## Constraints
- {time, money, dates, how they like to work}

## Out of scope
- {nearby things they don't want to chase now}
```

One mission per topic, concrete, under a screen. If the learner can't say why, ask before writing.
When the goal moves, confirm with them, update the file and write a learning record.

## RESOURCES.md

```md
# {Topic} Resources

## Knowledge
- [Kind: title, by author](url)
  One line: what it covers and when to reach for it.

## Wisdom (communities)
- [name](url)
  One line: what to bring there.

## Gaps
- {what the mission needs that no good source covers yet}
```

High trust only: primary sources, recognized experts, well-moderated communities. Every entry gets its
line. Prune what proved wrong or shallow. If the learner doesn't want communities, write that here.
Lessons take their facts from these sources, not from memory.

## Learning records

`learning-records/0001-<slug>.md`, numbered one past the highest. The whole format:

```md
# {What was learned or established}

{1-3 sentences: what is now known about the learner, and why it changes what to teach next.}
```

Add `Evidence:` (how it was shown), `Implications:` (what it unlocks or rules out) or
`Status: superseded by 0007` only when they help. Write one when a grade shows real understanding of
something non-trivial, a stated prior knowledge (with its claimed depth, still a hypothesis until a
probe shows it), a corrected misconception, the kind of mistake behind a stall (PROTOCOL section 6),
or a moved mission. Material merely covered is not a record; neither is a session log.

## GLOSSARY.md

```md
# {Topic} Glossary

{One or two sentences on what the topic covers.}

## Terms

**Preterite**:
The past tense for a finished action with a clear end: "ayer comí paella".
_Avoid_: simple past, perfect
```

A term goes in only once the learner has used it correctly without notes. Pick one word per idea and
list the others under _Avoid_. One or two sentences, saying what it is. Use glossary terms inside
definitions, and in every lesson once a term is here. Revise in place as understanding deepens.

---

Adapted from the `teach` skill in [mattpocock/skills](https://github.com/mattpocock/skills)
(`skills/productivity/teach/*-FORMAT.md`, commit `4ae2317`), under this license:

> MIT License
>
> Copyright (c) 2026 Matt Pocock
>
> Permission is hereby granted, free of charge, to any person obtaining a copy of this software and
> associated documentation files (the "Software"), to deal in the Software without restriction,
> including without limitation the rights to use, copy, modify, merge, publish, distribute,
> sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:
>
> The above copyright notice and this permission notice shall be included in all copies or
> substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT
> NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND
> NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES
> OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
> CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
