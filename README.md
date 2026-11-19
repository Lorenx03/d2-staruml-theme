# StarUML-style class, use case and activity diagrams with d2

Write UML class diagrams, use case diagrams and activity diagrams in plain [d2](https://d2lang.com),
mark stereotypes and relationship kinds with comments, and get an SVG that looks
like StarUML:

- bundled fonts (Inter by default), left-aligned members, bold class names,
  compartment lines
- `«stereotype»` lines, with the boundary/control/entity icons and colours
- thin black borders, a soft grey shadow
- UML arrowheads: open arrows, hollow triangles, diamonds
- use case diagrams: stick-figure actors, use case ellipses, a system box,
  dashed `«include»`/`«extend»` arrows ([below](#use-case-diagrams))
- activity diagrams: rounded actions, initial/final nodes, decision diamonds,
  fork/join bars with straight flows, `[guards]` ([below](#activity-diagrams))

```sh
uv run d2-staruml                               # every diagram in diagrams/ -> out/
```

## Requirements

- **[uv](https://docs.astral.sh/uv/)**: runs the tool (`brew install uv`).
  It needs no packages beyond the Python standard library.
- **d2 v0.9**: `brew install d2`
- **rsvg-convert**: only for PNG output (`brew install librsvg`)

Fonts come with the repo (`fonts/`), so nothing has to be installed and the
output looks the same on every OS.

## Using it anywhere

Install the command once, from the project folder:

```sh
uv tool install --editable .   # puts d2-staruml in ~/.local/bin
```

Then, from any folder:

```sh
d2-staruml path/to/dir -o path/to/svgs   # every .d2 in dir (and sub-folders) -> svgs/
d2-staruml path/to/dir                   # ... -> ./out/
d2-staruml path/to/dir --png             # PNGs instead
```

The install is editable, so it keeps using this folder's code, fonts and
icons: changes here apply straight away, and the project folder must stay
where it is (if you move it, run the install again). `uv tool uninstall
d2-staruml` removes it.

## Usage

Diagrams live in `diagrams/` (sub-folders are fine); renders go to `out/`,
mirroring the same sub-folders. `out/` is gitignored and created when missing.
Run the commands from the project folder.

```sh
uv run d2-staruml                               # all of diagrams/**/*.d2 -> out/**/*.svg
uv run d2-staruml --png                         # ... as PNGs (2x)
uv run d2-staruml class_diagram                 # just diagrams/class_diagram.d2
uv run d2-staruml class_diagram pairing_example # several by name
uv run d2-staruml diagrams/sub/foo.d2           # by path (must be inside diagrams/)
uv run d2-staruml --layout elk                  # override the layout engine
uv run d2-staruml --font Outfit                 # another font from fonts/
```

With a single diagram:

```sh
uv run d2-staruml class_diagram -w              # live preview in the browser
uv run d2-staruml class_diagram -o any/path.svg # explicit output path (.svg or .png)
uv run d2-staruml class_diagram --emit-d2 x.d2  # also save the generated d2
```

When one diagram fails (with its file and line), the others are still
rendered and the command exits with an error. `--diagrams-dir`/`--out-dir`
(or `STARUML_DIAGRAMS_DIR`/`STARUML_OUT_DIR`) change the two folders.

### Fonts

Each folder in `fonts/` is one font family, as downloaded from
[Google Fonts](https://fonts.google.com) (with its `OFL.txt` licence).
`--font NAME` (or `STARUML_FONT`) picks one by folder name, any case; the
default is `Inter`. To add a font, unzip the Google Fonts download into
`fonts/<Name>/`. The tool needs a static Regular and Bold file, in the folder
or its `static/` sub-folder (`Name-Regular.ttf`, `Name-Bold.ttf`). d2 can't
use variable fonts, so those are ignored. Inter ships several optical sizes,
so the smallest one (`18pt`, made for text) is used.

`--font` also takes a path to any folder with one family, e.g. a folder with
your own `Arial.ttf` and `Arial Bold.ttf`. Don't commit fonts whose licence
doesn't allow sharing them (Arial's doesn't).

The live preview (`-w`) re-renders on every save. It skips the final SVG
touch-ups, so it shows filled arrowheads and a blue shadow; the exported
file is correct.

## Writing a diagram

Everything is normal d2, so the same file also renders with plain `d2`, just
without the StarUML look.

```d2
direction: right

# <<entity>>
Person: {
  shape: class
  -id: int
  -name: string
  +getName(): string
}

EnrollmentService: {  # <<control>>
  shape: class
  +register(student\: Person): bool
}

# <<enumeration>>
Status: {
  shape: class
  ACTIVE
  SUSPENDED
}

Student -> Person              # <<gen>>
EnrollmentService -> Course    # <<dep>>
Lesson -> Course: {source-arrowhead.label: "1..*"; target-arrowhead.label: 1}  # <<comp>>
Student -- Course: enrolls in
```

### Classes

- A class is a `shape: class` block. Each line is a member, shown exactly as
  written.
- Lines with `(` are **operations**; the others are **attributes**. Each kind
  gets its own compartment, in the order you wrote them.
- In an `<<enumeration>>`, every line is a literal, in a single compartment.
- Write `\:` for colons inside parameter lists (`+f(a\: int): void`). The
  converter handles a bare `:` too, but plain `d2` would cut the member at it.
- `Person: "Display name" { … }` shows "Display name" as the class name.
- `style.fill: "#hex"` inside a class overrides its box colour.

Empty compartments are drawn automatically, like StarUML does: a bean with
only attributes gets an empty operations compartment, a control with only
operations gets an empty attributes compartment.

### Stereotypes

Put `# <<name>>` on the line(s) right above the class, or at the end of its
opening line (`Name: {  # <<name>>`). A blank line between the comment and the
class breaks the link.

| Stereotype                      | Box                                    |
| ------------------------------- | -------------------------------------- |
| *(none)*                        | white, no stereotype line              |
| `<<boundary>>`                  | light blue, boundary icon              |
| `<<control>>`                   | light pink, control icon               |
| `<<entity>>`                    | light yellow, entity icon              |
| `<<bean>>`                      | white                                  |
| `<<enumeration>>` / `<<enum>>`  | white, literals instead of members     |
| `<<interface>>`                 | white                                  |
| anything else, e.g. `<<dao>>`   | white, with that stereotype line       |

`# «entity»` works too, if you have the guillemets handy. A block with a
stereotype comment is treated as a class even without `shape: class`.

### Relationships

Put `# <<kind>>` at the end of the edge (or on the line above it):

| Kind      | Alias            | Write it as          | Drawn as                           |
| --------- | ---------------- | -------------------- | ---------------------------------- |
| *(none)*  |                  | `A -- B`             | plain line                         |
| `assoc`   | `association`    | `A -> B`             | line + open arrow at B             |
| `dep`     | `dependency`     | `A -> B`             | dashed line + open arrow at B      |
| `gen`     | `generalization` | `Child -> Parent`    | line + hollow triangle at Parent   |
| `real`    | `realization`    | `Class -> Interface` | dashed line + hollow triangle      |
| `comp`    | `composition`    | `Part -> Whole`      | line + filled diamond at Whole     |
| `aggr`    | `aggregation`    | `Part -> Whole`      | line + hollow diamond at Whole     |

- **Composition and aggregation are written part → whole.** d2 never draws
  an arrowhead at the *source* end of a `->`, so the diamond goes on the
  target end.
- Labels, multiplicities and role names are plain d2 and are kept:
  `A -> B: owns {source-arrowhead.label: 1; target-arrowhead.label: "0..*"}  # <<comp>>`.
- An edge without a kind comment keeps any d2 styling you gave it. It only
  gets the thin black line, and its `arrow` heads become open "V" heads.
- An unknown kind prints a warning and draws a plain line.

### Layout

d2's default engine is **dagre** (compact boxes, curved diagonal lines). For
**ELK** (right-angle lines), add this to the diagram, or pass `--layout elk`:

```d2
vars: {
  d2-config: {
    layout-engine: elk
  }
}
```

If ELK draws a label over a box, change the order the edges are declared in.
ELK lays edges out in that order. In `diagrams/class_diagram.d2`, declaring
`Student -- Course` before `Student -> Person` moved the "enrolls in" label
off Person's border. ELK can also make a box taller than its content when
many edges attach to it; dagre doesn't.

### Packages

Classes and edges inside containers (`pkg: { … }`) are converted too.
Everything that isn't a class or an edge is passed through unchanged.

## Use case diagrams

Put `# <<usecase diagram>>` anywhere at the top level of the file
(`use-case diagram`, `use_case diagram` work too). Without it, a file is a
class diagram.

```d2
# <<usecase diagram>>
direction: right

# <<actor>>
Operator

Jazebo: {
  drive: Drive robot
  script: Execute script
  pair: Pair with robot

  script -> drive  # <<extend>>
  drive -> pair    # <<include>>
}

# <<actor>>
Motion: Motion-control system

Operator -> Jazebo.drive
Jazebo.drive -> Motion
```

In a use case diagram:

| You write                                    | Drawn as                              |
| -------------------------------------------- | ------------------------------------- |
| `# <<actor>>` above a shape, or `shape: person` | stick figure, bold name below       |
| a shape with shapes inside (`Sys: { … }`)    | system box, bold name at the top      |
| any other shape (`drive: Drive robot`)       | use case: ellipse, bold name          |
| `A -> B`                                     | association: line + open arrow        |
| `A -- B`                                     | association without arrow             |
| `A -> B  # <<include>>`                      | dashed + open arrow, labelled «include» |
| `A -> B  # <<extend>>`                       | dashed + open arrow, labelled «extend»  |
| `A -> B  # <<gen>>`                          | generalization (hollow triangle)      |

- `# <<usecase>>` and `# <<system>>` (or `<<subject>>`) force the kind,
  e.g. for an empty system box.
- **«extend» goes from the extending use case to the base one**
  (`script -> drive`); «include» from the base one to the included one.
- A shape used in an edge but never declared (`Operator -> Drive robot`)
  becomes a use case. Declare actors explicitly.
- Write a label to replace «include»/«extend»: `a -> b: custom  # <<include>>`.
- Classes (`shape: class`, or another stereotype such as `<<entity>>`) are
  still drawn as classes.
- Each use case oval is fitted to its name, measured with the Bold font
  (`width`/`height` inside the shape override it).
- ELK (`--layout elk`) puts primary actors on the left and secondary ones on the
  right, like the usual StarUML layout. Dagre puts the actors above the system.
- With ELK, use case diagrams get tighter spacing than d2's defaults, so they
  are less wide: 40px between columns (instead of 70), 20px between edges and
  shapes (40) and 30px inside the sides of the system box (50). The box also
  gets extra room at the top (80 instead of 50), so edges to actors placed high
  up stay inside it instead of running along its top border. The values are
  `UC_ELK` in `src/style.py`.

## Activity diagrams

Put `# <<activity diagram>>` anywhere at the top level of the file.

```d2
# <<activity diagram>>

start  # <<initial>>
select: Select robot to control
port_ok  # <<decision>>
error: Display wrong port error message
fork  # <<fork>>
send: Send command to robot
wait: Wait while command is executing  # <<time>>
monitor: Monitor telemetry
join  # <<join>>
end  # <<final>>

start -> select -> port_ok
port_ok -> error: wrong port
error -> select
port_ok -> fork: good port
fork -> send -> wait -> join
fork -> monitor -> join
join -> end
```

The stereotype goes at the end of the node's line, or on the line above it.

| You write                              | Drawn as                                    |
| -------------------------------------- | ------------------------------------------- |
| any shape (`send: Send command`)       | action: rounded box, bold name at the top   |
| `# <<initial>>`                        | filled black circle                         |
| `# <<final>>`                          | circle with a black dot (activity final)    |
| `# <<flow final>>`                     | circle with a cross                         |
| `# <<decision>>` / `# <<merge>>`, or `shape: diamond` | small diamond, no name       |
| `# <<fork>>` / `# <<join>>`            | black bar spanning the flows it splits/joins |
| `# <<time>>` (or `<<wait>>`)           | hourglass, bold name below (time event)     |
| a shape with shapes inside             | rounded frame, bold name at the top         |
| `A -> B`                               | control flow: line + open arrow             |
| `A -> B: label`                        | the label is the guard: `[label]`           |

- Guards get their brackets added; one already in brackets must be quoted,
  `d -> b: "[else]"`, because d2 reads a bare `[…]` as a list.
- A decision with a name (`d: port ok? {shape: diamond}`, or a label after
  `# <<decision>>`) shows it beside the diamond.
- A shape used in an edge but never declared (`start -> Do something`)
  becomes an action, so declare the other kinds of node explicitly.
- Fork/join bars lie across the flow: horizontal with d2's default
  `direction: down`, upright with `direction: right`/`left`. They are drawn
  short and stretched afterwards (in the SVG) to reach 30px past the outermost
  flow that enters or leaves them (less if a shape beside them is in the
  way), and those flows become straight lines, square to the bar. A flow
  whose straight line (or the bar stretched to meet it) would run into
  another shape keeps the route the layout engine gave it.
- Activity diagrams use **ELK** unless you pick an engine (`--layout`, or
  `layout-engine` in the file): right-angle lines, like StarUML.
- **Loops are handled for you.** A layout engine has to turn one edge of
  each loop round to lay the graph out in layers, and ELK picks the wrong
  ones (the start of the activity ends up at the bottom). So the converter
  walks the flow from the initial node, in the order the edges are written,
  and writes each edge that goes back to a node already on the path the
  other way round: `error -> retry` becomes `retry <- error`. It is drawn
  the same (the arrow still points at `retry`), but the engine now lays
  `retry` above `error`. A chain (`a -> b -> a`) with such an edge is split
  into single edges. Write the flows the way they go; loops should go back
  to a `<<merge>>` node, as in StarUML.
- Classes (`shape: class`, or a class stereotype like `<<entity>>`) are still
  drawn as classes.

## Examples

In `diagrams/`:

- `class_diagram.d2`: small diagram, ELK layout
- `pairing_example.d2`: a full BCE diagram (boundaries, controls, entities,
  beans, enumerations), ELK layout
- `usecase_example.d2`: a use case diagram (actors, system, «include»,
  «extend»), ELK layout
- `activity_example.d2`: an activity diagram (decisions and merges, loops,
  fork/join, a time event, guards), ELK layout

Render them with `uv run d2-staruml` (output goes to `out/`, which is gitignored).

## Limitations

- Abstract classes can't be shown in italics (see the font trick below).
- Multiplicities and role names come out bold: d2 always draws them in
  italic, and the font trick turns italic into bold.
- d2's free layout engines draw either curves (dagre) or right angles (ELK),
  not StarUML's straight diagonal lines.
- Edge labels that cover each other, or another edge's line, are moved (see *Post-process*
  below). When an edge has no free spot left, its label stays where it was:
  shorten it.
- A reference to an edge that the converter turned round
  (`(error -> retry)[0].style…`) no longer finds it.
- An attribute written without a visibility prefix and named like a d2
  keyword (`label`, `icon`, `tooltip`, `link`, `near`, `class`) is read as
  the keyword. Add `+`/`-`/`#`/`~` in front.

## How it works

```
diagrams/         # your .d2 files
out/              # renders (gitignored)
src/
  cli.py          # the `d2-staruml` command: validate -> convert -> d2 -> post-process
  convert.py      # plain d2 -> styled d2
  style.py        # colours, stereotypes, sizes, edge kinds
  postprocess.py  # SVG touch-ups
  fonts.py        # finds the font files in fonts/
  icons/          # boundary / control / entity / actor / hourglass icons
fonts/            # bundled font families (OFL)
tests/            # uv run python -m unittest discover -s tests
```

0. **Validate.** `d2 validate` checks your file first, so syntax errors
   point at your own lines.
1. **Convert.** `convert.py` scans the d2 source and rewrites each class as a
   one-column grid (`grid-columns: 1; grid-gap: 0`), one cell per line:
   stereotype (with icon), name, separators, members, bottom padding. d2's
   own `shape: class` can't be restyled: it uses a monospace font,
   right-aligns types and has no stereotype line. Edges with a kind comment
   get their arrowheads and dashes. In a use case diagram, shapes become
   ovals, `shape: image` actors (`icons/actor.svg`) or a system container
   instead (ovals are sized from the name's width in the Bold font,
   read from the font file by `fonts.text_width`). The result goes to a hidden
   `.<name>.staruml.d2` next to your file, so relative imports keep working.
   It is deleted afterwards; `--emit-d2` keeps a copy.
2. **Render.** `d2` renders that file with the fonts swapped:
   - d2 v0.9 measures all text with the bold font, so left-aligned text
     drifted right as lines got longer. The Regular font goes in d2's "bold"
     slot, so text is measured exactly.
   - the Bold font goes in the "italic" slot; class names use italic to come
     out bold.
3. **Post-process.** `postprocess.py` edits the SVG:
   - replaces d2's filled arrowheads with open ones
   - turns the blue-grey shadow grey
   - moves an edge label that covers another one, or hides another edge's
     line: it slides along its own edge to the nearest spot clear of other
     labels and shapes (and, if there is one, of other edges' lines), together with the rectangle in d2's
     `<mask>` that hides the line under it. The layout engines put labels
     on top of each other, e.g. the guards of two flows leaving a decision
     at the same height.
   - activity diagrams: stretches fork/join bars (shapes with the d2 class
     `staruml-bar`) to span their flows and straightens those flows; adds
     the dot of final nodes and the cross of flow-final nodes (classes
     `staruml-final`, `staruml-flow-final`). d2 names each shape's and edge's
     `<g>` by its base64-encoded id, followed by its classes, which is how
     they are found.
   - for PNG, points the text at the family `StarUML Text`. `rsvg-convert`
     can't read the fonts embedded in the SVG, so it runs with a throwaway
     fontconfig that knows only the two bundled files under that name
     (`PANGOCAIRO_BACKEND=fc` makes pango use fontconfig on macOS too).

Separators are cells with a gradient fill: transparent except for a 1px black
band. d2 cells have no padding, so this is what leaves space above and below
each compartment line. Each member cell gets a generated key (`m1`, `m2`, …).
That's because d2 keys are case-insensitive, so two identical members, or an
enum literal like `END`, would otherwise merge with each other or with an
internal key.
