# The first thirty days

Launch is a different measurement problem from steady state. Answer quality
improves quietly and incrementally, and the quality measures below are the
ongoing bar for it — but in a launch window the risk is not that an answer is
subtly wrong. It is that the experience leaves an impression bad enough that
nobody comes back to find out. A first impression does not get a second
chance the way an answer does. So the one metric worth watching in the first
thirty days is repeat use: people who come back for a second session rather
than trying the system once and moving on.

## How it would be measured

The approach, not instrumentation that exists yet: issue an identifier to the
browser and keep it locally, so a returning browser can be recognized without
an account or a login. A session ends after a period of inactivity, the usual
boundary for turning a stream of requests into countable visits. Repeat use is
then whether a given identifier's second session happens at all, and how long
after the first.

## What the number needs to mean something

The corpus this system is demonstrated against holds ten people's worth of
meetings. That size was chosen to keep corpus generation tractable — it says
nothing about the organization this measurement is designed for. At ten
people, neither direct feedback nor telemetry produces enough events to read:
a handful of sessions from a handful of people is anecdote, not a rate, and
the number would not mean anything here.

The approach assumes a larger organization, at the scale telemetry is
normally read at. At that scale, three things change. Rates become readable
instead of counts of one or two events. Week-over-week movement stops being
explainable by one person's vacation or one team's offsite. And the quality
measures underneath — the diagnostic layer described below — gain a
denominator worth dividing by: a correction rate or an abstention rate is a
ratio, and a ratio needs enough queries in it to move for a reason rather than
by chance.

## The diagnostic layer underneath

Retention says that something is wrong. It does not say what. The system
already records the measures that answer that question for the queries
underneath a retention number: whether an answer abstained rather than
guessing, the citations an answer rests on, and the record a person leaves
behind when an answer misses — a gap the record didn't settle, a correction
naming what was wrong and what's right instead, or a thumbs up or down. A
retention dip with a rising correction rate reads differently than the same
dip against a flat one, and that's the reading these numbers are for.
