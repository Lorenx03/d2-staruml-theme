---
name: d2-staruml
description: Write UML class diagrams, use case diagrams and activity diagrams in d2 and render them to StarUML-style SVG/PNG with the `d2-staruml` command. Use when the user asks for a class diagram, a use case diagram, an activity diagram, a BCE (boundary/control/entity) diagram, a StarUML-looking diagram, or to render/compile .d2 files to SVG.
---

# d2-staruml

`d2-staruml` turns plain d2 class, use case and activity diagrams into
StarUML-looking SVGs: bold class names, compartment lines, `«stereotype»`
lines with BCE icons and colours, UML arrowheads, stick-figure actors,
use case ellipses, rounded actions, decision diamonds and fork/join bars. It needs `d2` on the PATH.

If `command -v d2-staruml` finds nothing, tell the user the tool isn't
installed. Don't install it yourself and don't fall back to plain `d2`:
plain d2 renders without the StarUML look.

## Rendering

```sh
d2-staruml path/to/dir -o path/to/svgs   # every .d2 in dir (recursive) -> svgs/, same sub-folders
d2-staruml path/to/dir                   # ... -> ./out/
d2-staruml path/to/dir --png             # 2x PNGs (needs rsvg-convert)
d2-staruml path/to/dir --layout elk      # right-angle edges (default engine: dagre, curved)
```

For a single diagram, pass `--diagrams-dir` (the folder that contains it)
plus the file:

```sh
d2-staruml --diagrams-dir docs docs/model.d2 -o model.svg    # explicit output file (.svg or .png)
d2-staruml --diagrams-dir docs docs/model.d2 --emit-d2 x.d2  # also keep the generated d2
```

`d2-staruml --help` lists every option.

- Files and folders whose names start with `.` are skipped.
- If a diagram fails, its error is printed with file and line. The others
  still render, and the command exits non-zero. Read the error, fix the
  `.d2` file, run the command again.
- `-w` (live browser preview) blocks until it is killed. Don't use it in an
  agent session.
- After rendering, report the paths of the files it wrote (`wrote …` lines).

## Writing a diagram

It is ordinary d2. Stereotypes and relationship kinds are **comments**.

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

- Use a `shape: class` block with one member per line, written exactly as it
  should appear. Lines with `(` are operations; the others are attributes.
- Escape colons inside parameter lists: `+f(a\: int): void`.
- Always give attributes a visibility prefix (`+ - # ~`). Without one, a name
  like `label`, `icon`, `link`, `near`, `tooltip` or `class` is read as a d2
  keyword.
- `Name: "Shown name" { … }` changes the displayed name.
  `style.fill: "#hex"` changes the box colour.

### Stereotypes

Write `# <<name>>` on the line directly above the class (no blank line in
between), or at the end of its opening line.

- `<<boundary>>`, `<<control>>`, `<<entity>>`: coloured box with an icon
- `<<enumeration>>` / `<<enum>>`: each line is a literal
- `<<interface>>`, `<<bean>>`, or any other name: white box with that
  stereotype line

### Relationships

Write `# <<kind>>` at the end of the edge.

| Kind   | Write it as          | Drawn as                       |
| ------ | -------------------- | ------------------------------ |
| none   | `A -- B`             | plain line                     |
| `assoc`| `A -> B`             | line + open arrow              |
| `dep`  | `A -> B`             | dashed + open arrow            |
| `gen`  | `Child -> Parent`    | hollow triangle at Parent      |
| `real` | `Class -> Interface` | dashed + hollow triangle       |
| `comp` | `Part -> Whole`      | filled diamond at Whole        |
| `aggr` | `Part -> Whole`      | hollow diamond at Whole        |

- **Composition and aggregation are written part → whole.** The diamond goes
  on the target end.
- Labels and multiplicities are plain d2:
  `A -> B: owns {source-arrowhead.label: 1; target-arrowhead.label: "0..*"}  # <<comp>>`.
- Packages are plain d2 containers: `pkg: { … }`.

### Use case diagrams

Start the file with `# <<usecase diagram>>`. Without it, the file is a class
diagram.

```d2
# <<usecase diagram>>
vars: { d2-config: { layout-engine: elk } }
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

- `# <<actor>>` above a shape (or `shape: person`): stick figure.
- A shape with shapes inside: system box, name at the top.
- Any other shape: use case (ellipse). An undeclared edge end
  (`Operator -> Drive robot`) also becomes a use case, so always declare
  actors.
- `A -> B`: association with open arrow. `A -- B`: no arrow.
- `# <<include>>` / `# <<extend>>`: dashed open arrow with the «include» /
  «extend» label. «extend» points from the extending use case to the base
  one. `# <<gen>>` works for actor/use case generalization.
- Use ELK for the usual StarUML layout: primary actors on the left, the
  system in the middle, secondary actors on the right.

### Activity diagrams

Start the file with `# <<activity diagram>>`. Activity diagrams use ELK by
default (right-angle lines); loops are turned round for the engine
automatically, so write every flow in the direction it goes.

```d2
# <<activity diagram>>

start  # <<initial>>
retry  # <<merge>>
select: Select robot to control
port_ok  # <<decision>>
error: Display wrong port error message
fork  # <<fork>>
send: Send command to robot
wait: Wait while command is executing  # <<time>>
monitor: Monitor telemetry
join  # <<join>>
end  # <<final>>

start -> retry -> select -> port_ok
port_ok -> error: wrong port
error -> retry
port_ok -> fork: good port
fork -> send -> wait -> join
fork -> monitor -> join
join -> end
```

- Any plain shape is an action (rounded box). Undeclared edge ends are
  actions too, so declare every other node with its stereotype.
- `<<initial>>`, `<<final>>`, `<<flow final>>`, `<<decision>>`/`<<merge>>`
  (or `shape: diamond`), `<<fork>>`/`<<join>>`, `<<time>>` (hourglass).
- Edge labels are guards: `d -> a: wrong port` shows `[wrong port]`. Quote a
  label that already has brackets: `d -> b: "[else]"`.
- Loops go back to a `<<merge>>` node, as in StarUML.
- Fork/join bars are stretched to span their flows automatically.
- A shape with shapes inside is a rounded frame with its name on top.

### Layout

Dagre is the default. To use ELK, add this to the diagram or pass
`--layout elk`:

```d2
vars: { d2-config: { layout-engine: elk } }
```

If ELK draws a label over a box, reorder the edge declarations; ELK places
edges in declaration order.

## Limitations

- Abstract classes can't be shown in italics.
- Multiplicities come out bold.
- Edges are curved (dagre) or right-angled (ELK), never straight diagonals.
- Edge labels that overlap, or sit across another edge's line, are moved
  along their own edge automatically; if one still
  overlaps (no free spot on its edge), shorten it.
