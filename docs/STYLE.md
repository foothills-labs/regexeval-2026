# House style

Two sources. The first is a marked-up pass over `ARTICLE.md` that came back
with the note *"the voice is absolutely gone"*, which tells us how the blog
register should sound. The second is five chapters of the lab's own thesis
writing, which tells us how the academic register should sound. Both were
read as evidence rather than as taste: every rule below is a thing that was
actually done, or actually cut, in one of those two bodies of text.

Read this before writing anything with a byline on it.

## What both registers share

**Findings first, commentary after.** The thesis states a definition, then
explains it: *"All this means is that the values of the function on the
boundary are given by..."* Never the reverse. Do not warm the reader up to a
result, state the result and then tell them what it means.

**The work is not the story of the work.** The thesis presents classical
solutions, shows where they are too restrictive, and moves to weak solutions.
That restrictiveness is a property of the problem, not an anecdote about the
author discovering it. When our own path is worth recording, it goes in a
methodology section or an appendix, and it is written as a property of the
method rather than as a confession. A headline that leads with what we got
wrong tells the reader we are the subject. We are not the subject.

**Confident first person plural.** *We define, we proceed, we can, we will,
we note.* Across fourteen thousand words of thesis there is not one hedge
about whether the authors are entitled to their conclusions. Limits are
stated as limits, not as apologies.

**No em dashes. No en dashes in prose.** Zero of either in the whole thesis.
Use a comma, a full stop, brackets, or a colon. Colons are the workhorse: a
hundred and fifty of them, mostly introducing the thing just promised. Semicolons
are nearly absent, five in total, and none of them were load bearing.

**No "not x, but y."** Zero instances. Antithesis as a rhetorical engine is
the single most reliable marker of writing that is performing rather than
explaining. Say the thing that is true, and stop.

**International spelling**, and consistently: *behaviour, analyse,
generalise, modelling*. Both `-ise` and `-ize` appear in the thesis, so this
is the one place the corpus does not settle it. Pick `-ise` and hold it.

**Sentence rhythm is mixed, not chopped.** Thesis mean is 20 words, with
about a fifth of sentences under ten. Long sentences carry the argument and
short ones land it. Three short sentences in a row is a tell, not a style.

## The academic register

For `paper/main.tex` and anything else with citations.

**Signpost with "Let us."** *Let us begin by defining a BVP formally. Let us
look at some examples of this behaviour. Let us now verify that.* It is the
thesis's most frequent construction and it does real work: it tells the
reader that a deliberate step is being taken, and by whom.

**Point forward, constantly.** *"A proper and extensive delve will be
provided into the weak formulation in chapter 2." "This property will become
very useful later on." "in the next section."* The reader should always know
that a loose end is a deliberate one. `\cref` is not a substitute for saying
out loud that something is coming.

**Light asides, never self-deprecating.** The thesis is not dry, it is warm,
and it manages that in about six phrases:

> Some good news is that all we require are the conditions above.
> This is a fancy way of saying...
> All of this theory is nice, but to really cement the importance...
> Now to change gears a little...
> It so happens that for our purposes...
> Of note is that the function depends heavily on context.
> Basically, by constructing a PDE in this form we get access to...

Notice what none of them do. Not one undercuts the result it introduces. The
aside is a hand on the reader's shoulder, not a wince.

**Dispatch limitations in one clause and move on.** *"The interaction between
the amount of restrictions is not in the scope of this work, but it is
sufficient for our purposes to say that in general we deal with BVPs with a
unique solution."* One sentence: what we are not doing, why it does not
matter here, next. A limitation that gets its own paragraph of hedging reads
as a weakness we have not thought through.

**Humour lives in footnotes.** *"I would cite the original text, which as far
as I can tell is..."* Never in the body.

**No contractions.** Zero in the thesis. Blog register is the opposite, see
below.

**Scare-quote new terms once with `\say{}`**, define them, then use them
plainly.

**Say why an object matters before defining it.** *"It is only proper to
start our deep dive into the finite element method by presenting and
explaining the very things we are trying to model."* One sentence of purpose,
then the formalism.

## The blog register

For `ARTICLE.md`. Same spine, looser clothing.

**Headings are lowercase.** `## what we did`, not `## What We Did`.

**Comma splices are allowed and are often better.**

> written: Nobody ships it on purpose. It shipped here because it passed its tests.
> kept:    Nobody ships it on purpose, it shipped here because it passed its tests.

Let sentences run into each other the way speech does.

**No confession-then-reveal set pieces.** A small admission of fault, then a
bolded turn, then an aphorism to close. Once is voice, six times is a tic,
and every instance after the first got cut.

> written: We came into this literature late, and most of what we assumed was
>          ours had already been done by somebody else. **Somebody already
>          built this benchmark.**
> kept:    **The benchmark already exists.**

The reader does not need to watch the realisation happen.

**Write what a person would say out loud.** "The question this project set
out to answer is how often that happens" became "We wanted to look at cases
like this."

**Not every paragraph needs a button.** Most should stop when the point is
made.

**Opinion, unhedged.** The equivalence library "is an excellent piece of
software in our estimation and deserves lots of love." Nothing in the data
says that. Say it anyway, and be generous about other people's work by name.

**Interest, out loud.** "The really nice thing about this is that none of it
needs a single API call." Tell the reader which parts you enjoyed.

**Stakes you can picture.** Not "at the point of use" but "on a system that
is failing at 5 am."

**Speculation, clearly marked.** Guessing at why a content filter behaves
oddly, hedged with "we think maybe," is allowed. Unresolved is allowed. The
register is a smart colleague thinking out loud.

**Human hedges are good**: "basically," "surprise, surprise," "yes, we ran
even more benchmarks," "at least as of late 2026."

**Callbacks are good.** "Ground truth continues to be hard" pays off a
heading from six sections earlier.

## Crutches to cut on sight

- "rather than" as a connective. It is almost always hiding a "not x, but y."
- "which is the point," "that is the finding," and any sentence whose only
  job is to tell the reader what they just read.
- "It is worth noting that." Note it.
- "In this section we will..." in the blog register. Just do it.
- Adverbs of emphasis: *crucially, notably, importantly, strikingly*. If it
  is crucial, the sentence will carry it.

## Length

The edited article was shorter overall while having longer sentences. Cut
structure, not texture.

## The test

Academic register: does it read like someone who knows the material teaching
it, warmly, to someone who will be examined on it? Blog register: does it
read like a person who did the work explaining it to someone they respect?
If either one reads like the abstract of a paper, or like a post that has
recently discovered antithesis, start again.
