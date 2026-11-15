# Credits

edu4self is small because it stands on other people's work. Thank you.

## Software it builds on

| what | by | used for | license |
|---|---|---|---|
| [`teach` skill](https://github.com/mattpocock/skills) (in `mattpocock-skills`) | Matt Pocock | inspired how edu4self runs a topic: mission, lessons, probes, learning records, glossary. The topic file formats in `plugin/skills/new-topic/FORMATS.md` are adapted from it, with its MIT notice. edu4self does not install or need it | MIT |
| [Claude Code](https://claude.com/claude-code) and its [plugin system](https://code.claude.com/docs/en/plugin-marketplaces) | Anthropic | the tutor, and how the skills are distributed | Anthropic's terms |
| [Puppeteer](https://pptr.dev) | Google and contributors | the browser tests (development only) | Apache-2.0 |

## Fonts (bundled in `app/dashboard/fonts/`, from [Google Fonts](https://fonts.google.com))

They are not covered by the MIT license in `LICENSE`. All four are under the [SIL Open Font License 1.1](https://openfontlicense.org); each license text ships
next to the font files. The files are unmodified; the CSS gives them local family names only.

| typeface | by | used for |
|---|---|---|
| [Oswald](https://github.com/googlefonts/OswaldFont) | Vernon Adams, Kalapi Gajjar, Cyreal | bar headings |
| [Libre Baskerville](https://github.com/impallari/Libre-Baskerville) | Impallari Type | bar body text |
| [IBM Plex Mono](https://github.com/IBM/plex) | IBM | bar numbers and small print |
| [Monoton](https://fonts.google.com/specimen/Monoton) | Vernon Adams | the neon sign |

## Radio

The jukebox lists four channels of [Radio Paradise](https://radioparadise.com), a listener-supported,
ad-free station founded by Bill and Rebecca Goldsmith, which publishes its stream addresses for other
players. edu4self links to the streams; it doesn't copy or host anything. If it keeps you company,
consider [supporting them](https://radioparadise.com).

## Ideas

- **Learning research.** Robert A. Bjork and Elizabeth L. Bjork (desirable difficulties; storage vs
  retrieval strength), Henry L. Roediger III and Jeffrey D. Karpicke (the testing effect), John Dunlosky
  and colleagues (which study techniques work). See [References](#references).
- ***Disco Elysium*** (ZA/UM). The bar view's dialogue, where your own skills talk to you, is a tribute
  to that game's design. edu4self uses its own characters, names, text and art; it is not affiliated with
  or endorsed by ZA/UM.
- **Timeboxing.** Focus blocks are ordinary timeboxing with free lengths. edu4self is not affiliated with,
  associated with, or endorsed by the Pomodoro Technique® or Francesco Cirillo, and does not use those
  marks.
- **[Obsidian](https://obsidian.md).** The vault layout works as an Obsidian vault, and notes can open
  there. Optional; edu4self is not affiliated with Obsidian.
- **[Contributor Covenant](https://www.contributor-covenant.org).** The basis of our code of conduct.

## References

- Bjork, R. A., & Bjork, E. L. (2020). Desirable difficulties in theory and practice. *Journal of Applied
  Research in Memory and Cognition*, 9(4), 475-479.
- Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham, D. T. (2013). Improving students'
  learning with effective learning techniques. *Psychological Science in the Public Interest*, 14(1), 4-58.
- Roediger, H. L., & Karpicke, J. D. (2006). Test-enhanced learning. *Psychological Science*, 17(3), 249-255.
- Wittbrodt, M. T., & Millard-Stafford, M. (2018). Dehydration impairs cognitive performance: a
  meta-analysis. *Medicine & Science in Sports & Exercise*, 50(11), 2360-2368. (Why the water rounds exist:
  the effect is small but real, and largest for attention.)
- Cirillo, F. Pomodoro® trademark guidelines. <https://www.pomodorotechnique.com/pomodoro-trademark-guidelines/>

## People

edu4self was built by [chillax97](https://github.com/chillax97) with Claude (Anthropic), from a personal
learning setup used daily before it was opened up. Contributors are listed in the git history.
