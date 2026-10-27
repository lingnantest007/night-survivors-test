# Project rules (CDT501 Lecture 9)

## The project
A small game in Python with pygame-ce. GAME.md is the design: read it first and follow its numbers.

## Files
- rules.py: the game rules with a fixed time step (1/60 s). No pygame in this file.
- data/game.json: all the numbers from GAME.md. Changing a number there must not need a code change.
- main.py: window, drawing, sound and input. The main loop is `async def main()` with
  `await asyncio.sleep(0)` once per frame, and the file ends with `asyncio.run(main())`,
  so pygbag can run it in a web browser.
- main.py must NOT import PIL, wave, make_assets or make_sounds (they do not work in a browser).
  It only loads finished files from assets/ and sounds/ (a sound can be .ogg or .wav: use whichever exists).
- make_assets.py (Pillow) and make_sounds.py (standard library) are separate scripts I run on my computer.
- tests/: tests with the standard library `unittest`.
- raw_art/: original pictures (Kenney, CC0). Never change, move or delete them.

## Rules for the agent
- Build only the step I ask for. Keep everything that already works.
- Use only Python's standard library, pygame-ce and Pillow. Ask before installing anything else.
- Only use pygame-ce functions and constants you are sure exist. If you are not sure, check with
  `python -c "import pygame; print(hasattr(pygame, 'NAME'))"`.
- Before you say it works: run `python -m unittest`, and run main.py without a window
  (SDL_VIDEODRIVER=dummy) in a way that also sends a few fake mouse moves, clicks and finger
  touches through the real event loop, so the input code runs at least once. Show me the real output.
- Explain what you did in simple English: I am learning to program.
- Do not run git commit unless I ask you to.
