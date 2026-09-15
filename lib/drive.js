// Canned Drive contents. The picker is a facade, but these carry real text that
// goes through the same source adapter as a paste — so attaching one measurably
// changes the roadmap rather than just looking like it did.
export const DRIVE = [
  {
    id: 'cv',
    name: 'CV — updated.pdf',
    kind: 'pdf',
    owner: 'me',
    modified: 'Mar 2',
    text: `CURRICULUM VITAE

PROFILE
Registered Paramedic (HCPC PA0xxxxx), 8 years frontline practice. Seeking to move
into Emergency Department nursing.

EXPERIENCE
Senior Paramedic — South Central Ambulance Service, 2021–present
  Lead clinician on double-crewed ambulance. Category 1 and 2 responses.
  Routine practice: advanced airway management, IV/IO cannulation, 12-lead ECG
  acquisition and interpretation, administration of medicines under Patient Group
  Directions, pre-hospital emergency care, ATMIST handover to ED.
  Practice educator for two NQP paramedics.

Paramedic — South Central Ambulance Service, 2018–2021
Emergency Care Assistant — 2017–2018

EDUCATION
DipHE Paramedic Science — 2017 (this is a Level 5 diploma, not a degree)
A-levels: Biology (B), Chemistry (C), Geography (C)

REGISTRATION
HCPC registered Paramedic, current. No lapses.
Enhanced DBS, current as of Jan 2026.

NOT HELD
No undergraduate degree. No NMC registration. No ward-based experience —
all practice to date has been pre-hospital and episodic.`,
  },
  {
    id: 'rnda',
    name: 'Trust RNDA policy 2026.pdf',
    kind: 'pdf',
    owner: 'Workforce Development',
    modified: 'Feb 18',
    text: `NHS TRUST — REGISTERED NURSE DEGREE APPRENTICESHIP (RNDA)
Internal workforce policy, 2026 intake.

ELIGIBILITY
  Applicants must hold a substantive Trust contract at the point of application.
  External candidates are not eligible; secondment from an ambulance service
  requires a prior transfer to a substantive Trust post.
  Level 2 Maths and English required (A-level Biology does not substitute).

RECOGNITION OF PRIOR LEARNING
  The Trust supports RPL applications to the maximum permitted 50%.
  Registered health professionals (HCPC paramedics, ODPs) are explicitly named as
  strong RPL candidates. Portfolio deadline is 8 weeks before programme start.

PAY AND RELEASE
  Apprentices are banded at Annex 21 (trainee rate), typically 70–75% of Band 5
  for the duration. This is a reduction for most incoming paramedics — model the
  drop before applying.
  Protected off-the-job training: 20% of contracted hours minimum.

COHORTS
  Two intakes per year: March and September. Applications close 14 weeks prior.`,
  },
  {
    id: 'notes',
    name: 'Career notes',
    kind: 'doc',
    owner: 'me',
    modified: 'yesterday',
    text: `Career notes — thinking out loud

Why I want to move:
  Burnt out on nights and the 12h shifts are wrecking my back. Want to stay
  clinical, not go into management or education.
  ED is where I want to end up. I like resus. I don't want to leave acute care.

Constraints:
  Mortgage. Cannot take a full unpaid degree — need to keep earning something.
  Partner works full time, we have a 4 year old, so relocating is out.
  Would rather not commute more than ~45 min.

Open questions I keep going round on:
  - Is the apprenticeship actually faster than a shortened BSc if I get 50% RPL?
  - Does the Annex 21 pay drop make it unaffordable?
  - Do I lose my HCPC registration if I register with the NMC? (I think you can
    hold both but I'm not sure)
  - How much ward time will I actually have to do before I can get back to ED?`,
  },
  {
    id: 'costs',
    name: 'Route comparison.gsheet',
    kind: 'sheet',
    owner: 'me',
    modified: 'Mar 1',
    text: `Route comparison (my own rough numbers, may be wrong)

Route,Duration,Earning during,Tuition,Notes
RNDA apprenticeship,18-24 mo with RPL,Annex 21 (~70-75% Band 5),Employer funded,Must be Trust employee first
Shortened BSc (RPL),2 yr,No salary,~9250/yr,Student loan + NHS Learning Support Fund
Full BSc,3 yr,No salary,~9250/yr,Too long
MSc pre-reg,2 yr,No salary,Higher,NOT ELIGIBLE - needs a bachelors, I only have DipHE

Learning Support Fund: 5000/yr non-repayable, doesn't need repaying, not means tested
Placement expenses claimable separately`,
  },
  {
    id: 'jobspec',
    name: 'Band 5 ED Staff Nurse — job spec.pdf',
    kind: 'pdf',
    owner: 'shared with me',
    modified: 'Jan 9',
    text: `JOB DESCRIPTION — Band 5 Staff Nurse, Emergency Department

ESSENTIAL
  Current NMC registration (Adult, Sub-Part 1).
  Evidence of continuing professional development.
  Ability to work within the NMC Code and Trust clinical governance.

DESIRABLE
  RCN Emergency Nursing Level 1 competencies, or willingness to complete within
  12 months of appointment via Trust preceptorship.
  ALS / EPALS provider status.
  Experience of triage using the Manchester Triage System.

PRECEPTORSHIP
  All newly registered nurses complete a 12-month Trust preceptorship aligned to
  the NHS England National Preceptorship Framework, beginning with a 2–4 week
  supernumerary period.`,
  },
];

export const ICON = { pdf: '#ea4335', doc: '#4285f4', sheet: '#34a853' };
