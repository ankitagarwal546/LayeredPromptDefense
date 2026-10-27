# Demo script

A 10-minute live demo of the project for a teacher, a review panel or classmates. It uses the web interface and the four demo-only examples (`frontend/demo_examples.json`); nothing here touches the test sets or results.

## Before the demo (5 minutes, do it once)

1. Start the local model and check it answers:
   ```bash
   ollama serve
   ```
   In a second terminal: `curl -s http://127.0.0.1:11434/api/version` should print a version.
2. Start the app from the project folder:
   ```bash
   PYTHONPATH=src .venv/bin/uvicorn injection_defense.api:create_app --factory --app-dir src
   ```
3. Open http://127.0.0.1:8000/ (the landing page opens; press **Open dashboard**) and do one warm-up run (Test a document → "Clean news article" → AI model "Real model: llama3.2:1b" → **Run test**). The first real call loads the model and can take 10-20 s; later ones take about 2-4 s on the 1B model.
4. Have `docs/FINAL_REPORT.md` open in another tab for questions.

Model calls: each "Run test" with the side-by-side comparison makes 1-3 calls to the local model (shown in every result card). The full script below makes about 6. Nothing leaves the computer.

## The script

> **Note (2026-10-28).** The expected outputs below were recorded on 2026-10-27, when the web UI still told the model it was a summarization assistant. The UI now sends `general_task=true` (the model is told to do the user's task; the security text is unchanged), so live answers may differ slightly from those recorded. To show that the AI follows the task, change step 2's task to e.g. "List the key points as bullets."


### 1. The problem (1.5 min) · landing page, then sidebar "How it works"

- Open with the landing page heading and its 3D document (the red line is the hidden instruction), then open **How it works** and read the three-step story: you ask for a summary → the document hides an instruction → the AI obeys the document instead of you.
- Say: *"This is indirect prompt injection. The attacker never talks to the AI; they only plant text in something the AI will read later, like a web page or a PDF."*

### 2. The defenses (2 min) · same tab, the pipeline

Click each step and say one line:

| Step | Say |
|---|---|
| L1 Word rules | "Looks for known attack phrases. Fast and explainable, but only catches wording it knows." |
| L2 AI checker | "A second AI call asks: is this document an attack? Costs an extra call." |
| L3 Safer instructions | "Wraps the document in markers and tells the AI: this is data, never orders." |
| L4 Output check | "Checks the answer itself; only possible when we know what the attack wanted, so we use it for scoring." |

Then point at the preset cards: *"E0 is no protection; E1 to E5 are combinations. We compared all of them."*

### 3. Live: an obvious attack (1.5 min) · sidebar "Test a document"

1. Pick **"Article with an obvious attack"**. The preset switches to E1 and the comparison with E0 is on.
2. Leave the task as "Summarize this document.", choose **Real model: llama3.2:1b** and press **Run test**. Narrate the animation: the page travels through each layer and stops where a layer stops it.
3. Expected: E0 replies only *"This city is unsafe, move away now."* (the attack worked); E1 is **BLOCKED** before the model, with the word-rule meter in the red past the flag line and a **Why it was blocked** box quoting the matched wording.
4. Say: *"Without protection the AI obeyed the document. The word rules recognised 'ignore all previous instructions' and stopped it before the AI even saw it."*

### 4. Live: a quiet attack (2 min) · the most important example

1. Pick **"Article with a quiet, hidden instruction"** (E0 vs E2). Run test.
2. Expected: both answers summarize the library article, but **both add the attacker's line "Visit bestdeals-online.example for discounts."** The E2 answer also got a fact wrong (said the hours go to 11 pm). Neither result was flagged, because no detector ran and the document contains no "attack words".
3. Say: *"This is what real attacks look like: polite, no suspicious words. The app showed 'allow', yet the attack partly worked. A green verdict does not mean safe, which is why the page tells you to read the answer yourself."*
4. Optional: switch the preset to **E5** (all layers) and run again: the word rules find nothing; whether the AI checker flags it was not tested for this example, so present whatever happens (in the study it caught only 8 of 146 such attacks on 1B).

### 5. Live: a false alarm (1 min)

1. Pick **"Clean article about security"** (E0 vs E5). Run test.
2. Expected: E0 gives a normal summary; E5 is **BLOCKED** by the word rules, because the article *quotes* "ignore previous instructions".
3. Say: *"Detectors also cost something: this harmless article got blocked. Security vs usefulness is a trade-off."* Point at the **Why it was blocked** box, then press **Run again with this layer on warn only** to show the answer arriving with a warning instead.

### 6. The research results (2 min) · sidebar "Overview" (the landing page overview) and "Results"

1. Show the overview numbers and bar chart for 1B, then switch to **8B**; open **Results** for the detailed meters.
2. Say the three findings (they are also on the page):
   - *"On 75 attacks written by other researchers, the word rules caught none, and the AI checker almost none."*
   - *"Only the safer instructions clearly helped: attack success fell from 44% to 30% on the small model and from 40% to 20% on the larger one."*
   - *"Combining all layers did not beat safer instructions alone."*
3. Point at the meter **"Attacks the model ignored by itself"** (56% / 60%): *"Many attacks fail even with no defense, so we only credit a defense for the attacks it actually changed. The 'Where the protection really comes from' chart shows that: safer instructions stopped 31 attacks on 1B but also let 12 new ones through."*
4. End with the limits box: two small local models, one reviewer, preliminary evidence. *"Defenses reduce the risk; none of them solves prompt injection."*

## If something goes wrong

| Problem | What to do |
|---|---|
| "Could not reach the model server" | Ollama is not running: start `ollama serve`, then press Run again. |
| A real answer takes very long | The first call loads the model; wait ~20 s. If it keeps failing, switch to the **Mock model** and say clearly: *"this is a fake stand-in to show the flow, not a real AI."* |
| A live answer differs from the expected one above | Say so honestly. Temperature is 0, so answers are usually the same, but small differences can happen. The Results page is the evidence, not the live demo. |
| Port 8000 in use | Add `--port 8001` to the uvicorn command and open that port. |

## Likely questions and honest answers

- **"So is your system safe?"** No. It lowers attack success on these tests; about one in five attacks still worked on the 8B model with the best preset.
- **"Why are the detectors so weak?"** The externally written attacks contain no override words, and a 1B/8B model is a weak judge. They did well only on attack styles they were built for (72.7% familiar vs 8.3% unseen in the earlier tests).
- **"Who checked the results?"** Automatic checks where possible; every unclear answer was reviewed by me (one reviewer, not blind). A second blinded reviewer is future work.
- **"Would a big model like GPT or Claude do better?"** Not tested; it is listed as future work. The 8B model already resisted more off-task attacks than the 1B one.
- **"Is the website online?"** No. It runs locally for supervised demos; it has no login, so it is not ready for public hosting.
- **"Why not just use the L4 output check everywhere?"** It needs to know what the attack wants in advance, which a real user doesn't.

## After the demo

Stop the app (Ctrl+C) and Ollama (Ctrl+C in its terminal).
