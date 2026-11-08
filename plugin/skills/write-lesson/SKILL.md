---
name: write-lesson
description: Write the next lesson, lesson part, redo or exercise for a topic in an edu4self vault and put it on the dashboard. Use whenever a lesson page is due, including when grading or a new topic unlocks one, or the plan needs its next unit written ahead.
argument-hint: "Which topic, and what should the lesson teach?"
---

A **lesson** is one short HTML page that teaches one idea and ends in closed-book exercises the learner
answers from the dashboard. Reading it is not proof; the graded answers are. Write it for: $ARGUMENTS

1. **Read before writing.** In the topic folder: `MISSION.md`, `NOTES.md` (how they like to be
   taught), `GLOSSARY.md`, `RESOURCES.md`, the newest `learning-records/`, `assets/`, and the last
   lesson. In the vault: `PLAN.md` (which unit this is and what comes after) and the active room
   (`theme` in `_system/config.json`). *Done when you can name the one idea, the learner's evidence
   that they're ready for it, and the source you'll teach it from.* Missing evidence of a prerequisite
   means a probe first (`write-probe` skill), not a lesson.
2. **Size it.** One idea, about 15 minutes, one tangible win tied to the mission. An idea that needs
   two new terms or two exercises of different kinds is two **parts**: each its own page, task and
   exercise, numbered `Lesson 05 · part 1`, `part 2`.
3. **Write the page** at `<topic>/lessons/NNNN-<slug>.html` (one past the highest number), in the
   shape of the vault's example lesson (`how-learning-works/lessons/0001-*.html`) or the topic's last
   lesson:
   - `<head>` links `../assets/lesson.css`; `quiz.js` loads at the end of `<body>`. Use the shared
     classes (`wrap`, `masthead` with `kicker`, `dek`, `meta`, `note`, `quiz`, `trace`, `formula`,
     `hint`, `nav`) and no colours or fonts of your own: the server lays the room's `lesson.css` over
     the page, and inline styling fights it.
   - Masthead: `Lesson NN · <topic> · milestone Mx`, the title, a one-line dek, prerequisites, a link
     to the cheat sheet and the minutes.
   - **Section 0, before you read:** one closed-book question on what's coming. A wrong guess here is
     part of the method.
   - Short numbered sections, each with an in-page `.quiz` for instant feedback. Options are the same
     length, and the right one moves position between questions.
   - Facts come from `RESOURCES.md`; cite them inline and list them under Sources. Point at one
     primary source worth reading next.
   - **Last section, "Exercises (submit these from the dashboard)":** "Close this page first," then
     numbered questions answered from memory: explain, apply, predict. None of them can be answered
     by copying a line of the page.
   - Words: plain and kind, in the topic's glossary terms. A themed aside fits only the learner's
     room and stays one line (see THEMES.md, "The one rule: stay in the room"); core words like
     Lesson 05, Exercises and Submit answers stay plain.
4. **Branches**, when they apply:
   - **Exercise with a checker** (code, calculations a script can check): a folder
     `<topic>/exercises/<task-id>/` with the learner's starter file, `check.py` beginning with the
     work-record lines from PROTOCOL.md section 6, and `HINTS.md` with one `## n · name` heading per
     hint, smallest nudge first. The spec in the page gives Input, Output, two worked Examples and
     Constraints per function. Test the checker on a copy of the folder outside the vault (inside it
     the runs would land in the learner's work record): the starter fails, your solution passes, and
     every Example's output is what you printed in the spec. Keep your solution out of the vault.
   - **Redo** of a missed lesson: a new short page that re-teaches the gap the grade found, opening
     with a one-screen refresher of the original idea (no exercise answers in it), then new exercises
     on the same skill.
5. **Keep the cheat sheet.** Add what's worth keeping to `<topic>/reference/NNNN-<slug>.html` and link
   it both ways.
6. **Put it on the dashboard.** Add the task to the topic's `queue` in `_system/state.json`
   (PROTOCOL.md section 3): `id` like `<topic>-lesson-05`, `kind: "lesson"`, `label`, `title`, a
   one-line `why`, `href: "/vault/<topic>/lessons/<file>"`, `effort` (minutes and exercises) and
   `submit: {type: "answers", intro: "Close the lesson first and answer from memory. Short is fine.",
   fields: [...]}` with one field per exercise, numbered as in the page. Add `exercise` for a checker
   folder, `calculator: true` only when the rules allow one. It is `todo` if it's the learner's next
   unit, otherwise `locked` with an `unlock` line.
7. **Plan and check.** Update `PLAN.md` (PROTOCOL.md section 5): the unit in its slot, a recall check a
   few units later, a line under Changes. Set `updated`, then run the check command from the vault's
   `CLAUDE.md`. (From the dashboard panel there is no shell: the server runs the check after you
   reply.)

**Done when** the page opens from its task link, every exercise has a matching `submit` field, the
check exits 0, and `PLAN.md` shows two units fully written: the learner's current one and the next.
Tell the learner what the lesson is for in one line and give its link,
`http://127.0.0.1:<port>/#submit=<task-id>`.
