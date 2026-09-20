# IEC 62443 Compliance Certification – Scope and Timeline

- **Date:** 2026-02-24
- **Attendees:** Priya, Marcus, Sofia, Callum, Renata

## Transcript

[Priya]: The reason I pulled this group together is that Meridian Industrial reached out last week and told Elena that IEC 62443 certification is now a hard procurement requirement for them starting in Q3. Meridian is one of our five largest accounts, so this is not optional. I want to understand what getting certified actually involves before we commit to anything.
[Callum]: I've done a preliminary read of the standard. IEC 62443 covers cybersecurity for industrial automation and control systems. For a sensor manufacturer in our position, the relevant part is mostly 62443-4-1, which is the secure product development lifecycle requirements, and potentially 62443-4-2, which covers technical security requirements for components. The certification process involves an accredited third-party assessment body. It is not a self-declaration.
[Marcus]: I was aware of the standard but I hadn't mapped our current development process against it. My honest first impression is that we're probably doing a lot of the right things informally, but we haven't documented them in a way that would satisfy an auditor.
[Sofia]: On the firmware side, I know we have gaps. We don't have a formal vulnerability disclosure process. Our secure coding guidelines exist but they're in a shared doc that hasn't been reviewed in about eighteen months. And I'm not sure our update mechanism meets the requirements for authenticated firmware updates.
[Callum]: The authenticated update requirement is one of the more technically specific items in 4-2. It's not just about having a signature — it's about the key management process around the signature. That's something the assessor will dig into.
[Renata]: Before we get too deep into the technical requirements, can someone give me a rough sense of what this costs? I need to know if we're talking about a fifty-thousand-dollar project or a five-hundred-thousand-dollar project because those have very different approval paths.
[Callum]: Based on what I've seen at other companies of our size, the assessment body fees alone are typically in the range of eighty to a hundred and twenty thousand dollars. That doesn't include the internal engineering time to close gaps, or any tooling or process changes. Total cost is hard to estimate without a gap assessment, but I would not be surprised if the all-in number is two hundred thousand dollars or more.
[Renata]: That's significant. Is there a phased approach where we could get to a credible interim position faster and cheaper, and then pursue full certification over a longer horizon?
[Callum]: Some customers accept a self-assessment against the standard as an interim measure while full certification is in progress. Whether Meridian would accept that is a question for Elena to raise with their procurement team. I can't answer it from a legal standpoint.
[Priya]: I'll have Elena ask them directly. But let's not assume they'll accept less than full certification, because if they won't, we need to be moving already.
[Marcus]: If we're going to pursue this seriously, the first thing we need is a formal gap assessment. I can't give you a timeline or a cost estimate without knowing exactly where we stand against the standard. I'd suggest we engage an external consultant to do that assessment — it'll take two to three weeks and it will give us a real picture.
[Sofia]: I agree with that approach. I can prepare an internal summary of our current firmware security practices before the consultant comes in, so we're not starting from zero. That'll make the assessment go faster.
[Callum]: I can help identify two or three accredited assessment bodies and get preliminary quotes. That way Renata has real numbers to work with for the budget approval.
[Renata]: That would help a lot. I'll need to bring this to Priya for a budget exception if it's above fifty thousand dollars total, and it sounds like it almost certainly will be.
[Priya]: I'm already aware it's going to need a budget exception. Let's not let the approval process slow down the information gathering. Marcus, how long would it take to close the gaps Sofia mentioned — the vulnerability disclosure process, the secure coding guidelines, and the firmware update authentication?
[Marcus]: The documentation gaps — vulnerability disclosure process, updated secure coding guidelines — I'd say four to six weeks with Sofia leading the work. The authenticated update mechanism is more involved. We'd need to design the key management infrastructure, implement it in firmware, and validate it. I'd estimate three to four months for that, and that's assuming we don't hit surprises.
[Sofia]: The key management piece is the one I'm least confident about. I've read the requirements but I haven't implemented anything like it before. We might need external expertise for that specific piece.
[Callum]: That's worth flagging to the assessment body early. Some of them offer technical advisory services alongside the assessment, which can be more efficient than bringing in separate consultants.
[Priya]: Okay, here's where I want to land today. Marcus and Sofia start on the documentation gaps now — don't wait for the gap assessment to fix things you already know are broken. Callum gets quotes from assessment bodies. I'll talk to Elena about the Meridian interim position question. Renata, please sketch out a budget range so we know what approval we're going to need.
[Renata]: Will do. One question I have that nobody has answered yet — what's the actual deadline? If Meridian's requirement kicks in Q3, when exactly do we need the certificate in hand?
[Marcus]: That's a good question. Q3 starts July 1st. If the assessment process alone takes three to four months, we would have needed to start the formal assessment in March to have any chance of being done by July. I think we're already behind if full certification by Q3 is the goal.
[Priya]: Then the Meridian conversation becomes even more important. We need to know if there's any flexibility on their end, or if we need to have a very direct conversation with them about what's realistic.
[Callum]: I'd recommend we get that answer before we commit to a specific timeline internally. Otherwise we might be engineering toward a deadline that turns out to be negotiable.
[Priya]: Agreed. Elena gets that conversation on her plate today.

## Decisions

- A formal third-party gap assessment will be initiated to determine the scope of work required for IEC 62443 certification.
- Known documentation gaps — vulnerability disclosure process and secure coding guidelines — will be addressed immediately without waiting for the gap assessment.
- Elena will be tasked with clarifying Meridian's actual deadline and whether an interim self-assessment would be accepted.

## Action items

- **Callum:** Identify two or three accredited IEC 62443 assessment bodies and obtain preliminary quotes for the gap assessment and full certification.
- **Sofia:** Prepare an internal summary of current firmware security practices to be ready before the external gap assessment begins.
- **Marcus:** Begin work on the vulnerability disclosure process and updated secure coding guidelines with Sofia.
- **Renata:** Sketch out a budget range for the certification project to determine what approval level will be required.
- **Priya:** Brief Elena on the Meridian certification requirement and ask her to clarify the deadline and interim acceptance question with Meridian's procurement team.
