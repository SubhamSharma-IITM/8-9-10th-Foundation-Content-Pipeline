# Research: Transformer Architecture & Long-Context Processing

**Date:** 2026-03-24
**Status:** COMPLETE — Critical findings for pipeline design

---

## The Core Problem: How Models Actually Process Long Inputs

### Self-Attention Is NOT Uniform

The attention mechanism computes: `Attention(Q, K, V) = softmax(QK^T / sqrt(d_k)) V`

This is inherently **competitive** — softmax creates a probability distribution. Tokens with higher dot-product scores get exponentially more attention. Three position-dependent biases exist:

1. **Attention Sinks** (Xiao et al., 2023): The first few tokens (BOS/system tokens) receive disproportionately high attention across nearly ALL heads and layers, regardless of content. This is a softmax artifact — the model uses initial tokens as a "dump" for attention mass.

2. **RoPE Decay** (Su et al., 2021): With Rotary Position Embeddings, the dot product between Q and K includes a term that **decays with relative distance**. Tokens far apart have a built-in penalty. This is by design (locality bias helps language), but it means distant tokens compete at a disadvantage.

3. **Layer Specialization** (Olsson et al., 2022): Lower layers → sharp, local attention (syntax). Higher layers → broader, semantic attention. Some heads specialize as "induction heads" (pattern copying), "positional heads" (fixed offsets), "retrieval heads" (semantic matching).

**Result:** The model does NOT linearly pay equal attention to each block of information.

---

## "Lost in the Middle" — The Exact Finding

**Paper:** Liu et al., 2023 (Stanford/UC Berkeley)

### U-Shaped Performance Curve

When relevant information is placed at different positions in the input:

| Position | Performance |
|----------|------------|
| Beginning (first 10-15%) | HIGH (~60%) |
| Middle (40-60% of context) | LOW (~40%) |
| End (last 10-15%) | HIGH (~58%) |

**Specific numbers (GPT-3.5-turbo, 20-document QA):**
- Position 1 (beginning): ~60% accuracy
- Position 10 (middle): ~40% accuracy
- Position 20 (end): ~58% accuracy
- **20 percentage point drop for middle positions**

### Why It Happens

1. **Recency bias**: Last tokens are "freshest" when generation begins. Strongest signal in residual stream.
2. **Primacy bias**: First tokens accumulate disproportionate attention (attention sink phenomenon).
3. **RoPE decay**: Middle tokens are maximally far from BOTH beginning (attention sinks) AND end (generation query).
4. **Training distribution**: Important info tends to appear at beginning (titles, topic sentences) or end (conclusions) in training data. Learned bias.

### Applies to ALL Models Tested
- GPT-3.5-turbo, Claude 1.3, MPT-30B, LongChat-13B — all showed U-shape
- Severity varied but pattern was universal
- Post-2023 models (Claude 3, Gemini 1.5+) improved for **retrieval** (needle-in-haystack) but the distinction matters...

### CRITICAL: Retrieval ≠ Comprehension

| Task | Long-context performance |
|------|------------------------|
| **Retrieval** (find a specific fact) | Modern models ace this even at 1M tokens |
| **Comprehension** (synthesize understanding from distributed content) | Degrades significantly, especially in middle sections |

**Our use case is COMPREHENSION, not retrieval.** We're asking the model to comprehensively extract ALL concepts from ALL sections — the harder task.

---

## Context Length Sweet Spots

| Range | Attention Quality | Notes |
|-------|------------------|-------|
| < 4K tokens | Excellent, uniform | Original training range for most models |
| 4K - 32K | Good | Models trained at these lengths handle well |
| 32K - 128K | Meaningful degradation | Synthesis quality drops, retrieval still works |
| 128K+ | Retrieval only | Comprehensive processing questionable |

**Key paper (Xiong et al., 2023, Meta):** Simply extending context via fine-tuning doesn't solve attention quality — model needs continual training on long-context data with tasks requiring full-context processing.

---

## How Thinking Budget Actually Works

### Two distinct phases:

**Phase 1: Prefill (Input Processing)**
- ALL input tokens processed in single forward pass
- Thinking budget does NOT change this
- The input is encoded identically regardless of LOW/MEDIUM/HIGH thinking
- This is where the U-shaped attention problem exists

**Phase 2: Thinking (Chain-of-Thought)**
- Model generates thinking tokens that **re-attend to the full input KV-cache**
- Each thinking token creates a NEW query vector → can attend to DIFFERENT parts of the input
- Higher thinking budget = MORE retrieval passes over the encoded input
- This is where thinking budget INDIRECTLY improves input processing
- The thinking phase acts as a "scratchpad" (Nye et al., 2021) that compresses and organizes information

**Phase 3: Output Generation**
- Benefits from intermediate representations built during thinking
- Thinking tokens serve as pre-processed summary, more easily attended to than raw input

### PROOF-READING-V5.0 Empirical Data

| Metric | MEDIUM (8192 tokens) | LOW (1024 tokens) |
|--------|---------------------|-------------------|
| Recall | 66% | 50% |
| Precision | 85% | 85% |
| F1 | 0.745 | 0.630 |
| False Negatives | 12/44 | 17/44 |
| Avg thinking tokens used | ~4,550 | ~0 (!) |
| Cost per question | Rs 0.48 | Rs 0.48 |

**Critical finding:** LOW budget produces **ZERO thinking tokens** — it doesn't actually think, just does fast inference. This explains lower recall. The model needs the thinking budget to re-attend to input and catch things it missed on prefill.

---

## Direct Impact on Our Pipeline

### The Danger

If we feed a full 30-page chapter (~15K-30K tokens of MD) and ask for concept extraction:
- **Beginning of chapter** (Ch 9: "Reflection of Light" intro) → WELL COVERED
- **Middle of chapter** (sign convention, mirror formula derivation) → AT RISK OF DILUTION
- **End of chapter** (lens formula, power of lens) → MODERATELY COVERED

This means the model will naturally produce a front-heavy concept distribution — exactly what the user flagged as a concern.

### Mitigation Strategies (Evidence-Based)

**1. Instruction BEFORE context (not after)**
- Place task description first, then context, then task reminder at end
- Model processes context with task already in residual stream → task-relevant attention during prefill
- The trailing reminder exploits recency bias

**2. Section markers (not line-by-line numbering)**
- Line_XXXXX numbering adds massive token overhead
- Better: number SECTIONS and PARAGRAPHS
- Creates distinct anchor tokens the model can attend to during thinking

```
## [SECTION 9.1] REFLECTION OF LIGHT
...content...
[END_SECTION 9.1]

## [SECTION 9.2] SPHERICAL MIRRORS
...content...
[END_SECTION 9.2]
```

**3. HIGH thinking budget for topology generation**
- More thinking tokens = more retrieval passes over the full input
- Topology is the backbone — worth the extra cost
- Use MEDIUM for content gen (shorter input, focused context)

**4. Two-pass chunked extraction (MOST EFFECTIVE)**

```
Pass 1: Process chapter in 3-4 overlapping chunks
  Chunk A: Sections 1-3 (with 1-paragraph overlap into 4)
  Chunk B: Sections 3-5 (with overlap)
  Chunk C: Sections 5-7 (with overlap)
  → Extract concepts from each chunk independently

Pass 2: Feed ALL extracted concepts back to model with full chapter
  → Deduplicate, merge, fill gaps
  → Verify every section has representation
```

This gives each section full attention quality in Pass 1, then uses the full context for synthesis in Pass 2.

**5. End with explicit checklist**
- "Verify you have extracted concepts from sections: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7"
- Forces the model to generate queries that attend to each section during thinking

**6. Section coverage validation (deterministic)**
- After topology generation, programmatically check: does every major section header from the MMD appear in at least one concept's line range?
- If sections are missing → re-prompt specifically for that section

---

## Gemini Model Configuration

**Model:** `gemini-3-flash-preview`

**Thinking budget levels:**
| Level | Tokens | Use case |
|-------|--------|----------|
| MINIMAL | 128 | Not useful (no real thinking) |
| LOW | 1,024 | Empirically produces 0 thinking tokens — avoid |
| MEDIUM | 8,192 | Good for content generation per subconcept |
| HIGH | 24,576 | Best for topology generation (full chapter comprehension) |

**Context caching pattern (from existing pipeline):**
- System prompt cached for 60 min (50% discount on subsequent calls)
- Chapter content as user message (cached separately)
- Per-subconcept queries against cached context

---

## Key Papers Referenced

| Paper | Year | Finding |
|-------|------|---------|
| Lost in the Middle (Liu et al.) | 2023 | U-shaped attention; middle content underprocessed |
| Attention Sinks (Xiao et al.) | 2023 | First tokens get disproportionate attention |
| Induction Heads (Olsson et al.) | 2022 | Specialized attention head patterns |
| RoPE (Su et al.) | 2021 | Distance-dependent attention decay |
| Gemini 1.5 (Reid et al.) | 2024 | MoE + long-context, near-perfect NIAH |
| Infini-attention (Munkhdalai et al.) | 2024 | Compressive memory for infinite context |
| Chain-of-Thought (Wei et al.) | 2022 | Intermediate reasoning improves quality |
| Scratchpads (Nye et al.) | 2021 | Working memory via intermediate tokens |
| Ring Attention (Liu et al.) | 2023 | Distributed full attention |
| YaRN (Peng et al.) | 2023 | RoPE extension for longer contexts |
| Effective Long-Context Scaling (Xiong et al.) | 2023 | Extension requires long-context training data |
