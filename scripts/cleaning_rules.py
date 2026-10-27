import re

EMOJI_NAME_LANGUAGE = "en"
SKIN_TONE_MODIFIERS = re.compile("[\U0001F3FB-\U0001F3FF]")

MIN_LETTERS_FOR_LANGUAGE = 3
LANGUAGE_REVIEW_RATIO = 1.5
LATIN_SHARE_MIN = 0.95
PRIOR_MIN_TOKENS = 5
WORD_MODEL_REVIEW_MARGIN = 1.0
LINGUA_TO_WORDFREQ_CODE = {"tl": "fil"}

SPAM_STRONG_PATTERNS = {
    "messaging_contact": (
        r"\bwa\.me/|\bt\.me/"
        r"|\b(on|via|at|through|me on|us on|her on|him on) (whats ?app|telegram|signal)\b"
        r"|\b(whats ?app|telegram)\s*[:@+]?\s*\+?\d"
    ),
    "self_promotion": (
        r"\b(check out|visit|subscribe to|watch|go to|head to|follow) (my|our) "
        r"(channel|page|profile|podcast|newsletter|website|site|blog|videos?|content)\b"
        r"|\blink in (my )?bio\b"
    ),
    "direct_message_bait": r"\b(dm|inbox|text|message|whatsapp) me\b",
    "advisor_scam": (
        r"\b(financial|investment) (advisor|adviser|coach|planner|expert|manager) "
        r"(named|called|by the name|is)\b"
        r"|\b(expert|licensed|certified|professional) (trader|broker|fx trader|account manager)\b"
        r"|\b(reach|contact|write to) (her|him) (on|via|through|at)\b"
    ),
    "trading_scheme": r"\bforex\b|\bbinary options?\b|\bcrypto (signals?|trading platform)\b",
    "earning_claim": (
        r"\b(earn|make|made|making|earned) \$?\d[\d,.]*k?\s*(usd|dollars)?\s*"
        r"(a|per|every|each) (day|week|month)\b"
    ),
    "giveaway_bait": (
        r"\$\d[\d,.]*k? giveaway\b|\bgiveaway (link|winner|starts?|is live)\b"
        r"|\bfree (iphone|gift ?cards?|robux)\b|\bsugar (daddy|mommy)\b"
    ),
}

SPAM_WEAK_PATTERNS = {
    "finance_advisor": r"\b(financial|investment) (advisor|adviser|coach|planner)\b",
    "portfolio": r"\bportfolio\b",
    "crypto": r"\b(bitcoin|btc|crypto|ethereum|eth)\b",
    "trading": r"\btrad(er|ers|ing)\b",
    "promo_cta": r"\bsubscribe\b|\bfollow me\b|\bsign up\b|\bclick (the|my|this) link\b|\bmy channel\b",
    "discount": r"\bdiscount\b|\bpromo code\b|\bcoupon\b",
    "guidance_offer": r"\b(mentor|mentorship|guidance|coaching)\b",
    "passive_income": r"\bpassive income\b",
    "look_up_person": r"\blook (her|him) up\b",
    "adult_or_giveaway": r"\bonlyfans\b|\bgiveaway\b",
}

SPAM_REVIEW_ALONE = {"passive_income", "look_up_person", "adult_or_giveaway"}

REFERENCE_DOMAINS = (
    "youtube.com", "youtu.be", "wikipedia.org", "doi.org", "arxiv.org",
    "x.com", "twitter.com", "reddit.com",
)
REFERENCE_SUFFIX_LABELS = ("gov", "edu", "ac")
PHONE_DEFAULT_REGION = "US"
URL_WORD_LABEL_MIN_ZIPF = 3.5
URL_WORD_TLD_MIN_ZIPF = 4.5

REPEATED_TEXT_MIN_COUNT = 3
REPEATED_TEXT_MIN_WORDS = 6
AI_TERMS = [
    r"\bai\b", r"\ba\.i\b", r"\bia\b", r"\bartificial intelligence\b", r"\bagi\b",
    r"\bllms?\b", r"\blarge language models?\b", r"\bchat ?gpt\b",
    r"\bgpt[- ]?\d", r"\bopen ?ai\b", r"\bclaude\b", r"\banthropic\b",
    r"\bgemini\b", r"\bcopilot\b", r"\bdeepseek\b", r"\bgrok\b",
    r"\bmachine learning\b", r"\bneural net\w*", r"\bgen ?ai\b",
    r"\bgenerative\b", r"\bchatbots?\b", r"\bautomat\w*", r"\brobot\w*",
    r"\baltman\b", r"\bnvidia\b", r"\bdata ?cent(er|re)s?\b",
    r"\balgorithms?\b", r"\bagents?\b", r"\bagentic\b",
]

AI_REFERENCE = [
    r"\bai\b", r"\ba\.i\b", r"\bia\b", r"\bartificial intelligence\b", r"\bagi\b",
    r"\bllms?\b", r"\blarge language models?\b", r"\bchat ?gpt\b", r"\bgpt[- ]?\d",
    r"\bopen ?ai\b", r"\bclaude( code)?\b", r"\bopus\b", r"\bsonnet\b", r"\bcodex\b",
    r"\bcursor\b", r"\bgemini\b", r"\bcopilot\b", r"\bdeepseek\b", r"\bgrok\b",
    r"\bmidjourney\b", r"\bmachine learning\b", r"\bneural net\w*", r"\bgen ?ai\b",
    r"\bgenerative\b", r"\bchatbots?\b", r"\bautomat\w*", r"\brobot\w*",
    r"\bagents?\b", r"\bagentic\b", r"\bmachines?\b", r"\bthe tech(nology)?\b",
    r"\bthese (tools|models)\b", r"\bthis (tool|tech|technology)\b", r"\bmodels?\b",
    r"\bvibe ?cod\w*",
]

IMPLICIT_USE = [
    r"\b(i|we) (\w+ )?(use|used|am using|are using|have been using) (it|them|this|these)\b",
    r"\b(it|this|they) (makes?|made|has made|helps?|helped|saves?|saved|writes?|wrote|does|did|handles?) (me|my|us|our)\b",
    r"\b(it|this) (can|could) (develop|write|do) (code|my|our)\b",
]

WORK_EXCLUSION_PHRASES = [
    r"\bsteve jobs\b",
    r"\b(great|good|nice|amazing|excellent|fantastic|brilliant|awesome|superb|terrific|"
    r"wonderful|decent|solid|fine|poor|bad|terrible|awful|horrible|lousy|lazy|shoddy|"
    r"sloppy|stellar|incredible|outstanding|impressive|top|hell of a|heck of a) (\w+ )?job\b",
    r"\bjob well done\b", r"\bkeep up the (good|great) (work|job)\b",
    r"\b(does|did|do|doing|done) (a|an|the|his|her|their) (\w+ ){0,2}job\b",
    r"\bget(s|ting)? the job done\b", r"\bjob of (trying|pretending)\b",
    r"\b(con|scam|bs|bullshit|piss|make ?up|grift|trick) artists?\b",
    r"\b(gas|coal|oil|wood)[- ]fired\b", r"\bfired up\b",
    r"\b(critical thinking|thinking|driving|reading|social|people|listening|comprehension|"
    r"communication|debate|debating|interview|interviewing|math|research) skills?\b",
    r"\bskill issue\b",
    r"\b(it's|its|it is|not|isn't|is not) (my|your|our) job to\b",
]

PERSONA_ROLE_WORDS = [
    "he", "he's", "hes", "his", "him", "she", "she's", "her", "host", "guest",
    "interviewer", "interviewee", "presenter", "speaker", "panelist",
    "this guy", "the guy", "this dude", "this woman", "this lady", "this man",
]
PERSONA_JOKE_ROLES = ["host", "guest", "interviewer", "interviewee", "presenter",
                      "speaker", "panelist", "this guy", "the guy", "this dude"]
PERSONA_REPLACEMENT_JOKE = r"\breplac\w* (the |this )?({subjects})\b"
PERSONA_CREDENTIAL = re.compile(
    r"\b(engineers?|programmers?|developers?|journalists?|pr|career|degree|background|"
    r"experts?|scientists?|qualified|credentials?|cv|resume|tech industry|in tech|"
    r"comms?|communications|podcasters?|blogger)\b")

OCCUPATIONS = (r"(people|humans?|workers?|employees?|staff|jobs?|devs?|developers?|programmers?|"
               r"coders?|engineers?|artists?|writers?|designers?|translators?|accountants?|"
               r"lawyers?|paralegals?|doctors?|nurses?|teachers?|radiologists?|drivers?|"
               r"cashiers?|juniors?|interns?|graduates?|us|you|me|everyone|humanity)")

REPLACEMENT_STRONG = [
    r"\b(take|takes|took|taking|steal|stealing|stole|kill|killing) (over )?(our|your|their|my|all|"
    r"all the|the|people'?s|everyone'?s|most|many|human|white collar|those|these)? ?jobs?\b",
    r"\b(lose|lost|losing|loses) (our|your|their|my|his|her|the)? ?(jobs?|livelihoods?|careers?)\b",
    r"\bjob (loss|losses|cuts?|market|displacement|security)\b",
    r"\bjobs? (will|would|are going to|are gonna|gonna|is going to|start) (\w+ )?"
    r"(disappear\w*|vanish\w*|be gone|be lost|go away|be replaced|be automated)\b",
    r"\b(no|fewer|few|less) jobs\b", r"\bjobs left\b", r"\bjobless\w*", r"\bunemploy\w*",
    r"\blay ?offs?\b", r"\blaid off\b",
    r"\bfir(e|ed|es|ing) (\w+ )?(people|workers|staff|employees|devs|developers|engineers|"
    r"coders|programmers|writers|artists|designers|everyone|half)\b",
    r"\b(out of work|out of a job)\b", r"\bubi\b", r"\buniversal basic income\b",
    r"\b(replac\w*|get(ting)? rid of|got rid of|sack\w*) (all |the |all the |most |many |real |our |"
    r"your |their |human )?" + OCCUPATIONS + r"\b",
    OCCUPATIONS + r" (are|is|will be|being|get|got|getting|were|was|gonna be|going to be) "
                  r"(\w+ )?(replaced|automated|obsolete|out of work)\b",
    r"\bkeep (my|our|their|your) jobs?\b",
    r"\binstead of (paying|hiring|employing) (\w+ )?(people|humans?|workers|someone|staff)\b",
    r"\b(cheaper|faster|better) than (hiring|paying|contracting|employing) \w+",
    r"\bautomat(e|ed|es|ing|ion) (\w+ ){0,3}(jobs?|workers|roles|positions)\b",
    # Nada netral/menyangkal: tetap masuk agar sikap "minimise" tidak hilang.
    r"\b(won'?t|will not|wont|isn'?t going to|is not going to|not going to|never going to|"
    r"can'?t|cannot|couldn'?t|doesn'?t|does not|didn'?t|did not) (\w+ ){0,2}"
    r"(replace|take|kill|eliminate|threaten|steal|destroy|wipe out) (\w+ ){0,2}"
    r"(jobs?|careers?|workers|employment|professions?)\b",
    r"\bjobs? (are|is|will be|remain|remains|stay|stays) (\w+ )?(safe|fine|secure)\b",
    r"\bjobs? (aren'?t|are not|isn'?t|is not|won'?t be|will not be) going anywhere\b",
    r"\b(fears?|panic|worr(y|ies)|concerns?|anxiety|alarm) (about|over|of) (\w+ ){0,3}jobs? "
    r"(is|are|seem|seems) (\w+ )?(overblown|exaggerated|overstated|unfounded|misplaced|overhyped)\b",
    r"\b(overblown|exaggerated|overstated|overhyped) (\w+ ){0,2}(job|jobs|unemployment|layoffs?|job loss\w*)\b",
    # Nada informatif: laporan penggantian tanpa penilaian.
    r"\b(replaced|cut|eliminated|laid off|let go|fired) (\d[\d,.]*k?|hundreds|thousands|dozens|"
    r"half|most|many|some) (of )?(\w+ ){0,2}(workers|employees|staff|jobs|agents|people|roles|"
    r"positions|engineers|developers|writers|designers)\b",
    r"\b(some|certain|many|most|routine|repetitive|simple|basic) (\w+ )?(tasks|jobs|roles|positions) "
    r"(will|can|could|might|may|are|is) (\w+ )?(be )?(automated|replaced|done by|handled by)\b",
]
REPLACEMENT_WEAK = [
    r"\b(obsolete|redundan\w*|displac\w*)\b",
    r"\b(white|blue)[- ]collar\b", r"\bworkforce\b",
    r"\b(human|cheap|manual|physical|skilled|unskilled) labou?r\b",
    r"\blabou?r (costs?|market|force|shortage)\b",
    r"\bhir(e|es|ed|ing) (\w+ )?(people|humans?|workers|staff|devs|developers|engineers|"
    r"programmers|juniors|graduates|interns|someone|anyone|a person|more)\b",
    r"\bheadcount\b", r"\boutsourc\w*", r"\boffshor\w*",
    r"\b(for|make|makes|making|earn|earns|earning) a living\b", r"\blivelihoods?\b",
    r"\bautomat(e|ed|es|ing|ion) (\w+ ){0,3}tasks?\b",
    r"\b(surpass|outperform|beat|outcompete|compete with)\w* (\w+ )?(humans?|people|workers|"
    r"programmers|devs|developers|engineers|coders|me|us)\b",
]
USE_STRONG = [
    r"\bat work\b", r"\b(my|our) (job|work)\b",
    r"\b(at|for|in) (my|our) (job|work|workplace|company|team)\b",
    r"\bproductivity (gains?|boosts?|increases?|improvements?|targets?)\b",
    r"\b\d+ ?x (more )?(productive|faster|output|productivity)\b",
    r"\bforced\b(\s+\S+){0,3}\s+(employees|workers|staff|engineers|developers|devs|coders)\b",
    r"\b(employees?|workers?|staff|coders|developers|devs|engineers|programmers) "
    r"(\w+ ){0,3}(forced|told|required|expected|mandated) to\b",
    r"\bforced\b(\s+\S+){0,6}\s+(employees|workers|staff)\b",
]
USE_WEAK = [
    r"\b(at|for|in) (their|your) (work|job|jobs|company|team|workplace|office|field|"
    r"industry|profession|business)\b",
    r"\bin (my|our) (field|industry|profession|business|office)\b",
    r"\b(my|our) (team|company|employer|boss|manager|clients?|coworkers?|colleagues?|"
    r"codebase|code base|business)\b",
    r"\b(i'm|i am|im|as) (also |just |actually )?an? (\w+ )?(software |senior |junior |lead |web |firmware |data )?"
    r"(engineer|developer|dev|programmer|coder|designer|writer|translator|accountant|lawyer|"
    r"attorney|nurse|doctor|teacher|artist|illustrator|analyst|consultant|manager|"
    r"filmmaker|editor|copywriter|marketer|freelancer|swe)\b",
    r"\bi work (in|at|as|for|with)\b", r"\bi('ve| have)? worked (in|at|as|for)\b",
    r"\b(employees?|workers?|staff|coders|developers|devs|engineers|programmers) "
    r"(\w+ ){0,3}(use|using|adopt\w*)\b",
    r"\b(writes?|wrote|writing|generates?|generated) (\w+ ){0,2}(of )?(my|our|all|most) code\b",
    r"\b(clients|customers) (don't|do not|won't|no longer) (value|pay|need)\b",
    r"\bprofessions?\b", r"\bdelegat\w*", r"\bproductiv\w*",
    r"\b(forced|mandated|required|told|pushed) to use\b",
    r"\b(use|using) (it|them|ai|claude|chatgpt|copilot|llms?) (\w+ )?(for|to) (code|coding|work|my|our)\b",
]
SKILLS_STRONG = [
    r"\b(de|up|re)skill\w*", r"\bretrain\w*",
    r"\bskills? (gap|shortage|atrophy|decline|erosion|loss)\b",
    r"\b(brain rot|cognitive (decline|offloading)|automation (complacency|bias))\b",
]
SKILLS_WEAK = [
    r"\b(my|our|their|your|his|her|human|people'?s?|workers'?|employees'?) (\w+ )?skills?\b",
    r"\bskilled (workers?|people|labou?r|trades?)\b", r"\bjuniors?\b", r"\bentry[- ]level\b",
    r"\binterns?(hips?)?\b", r"\bapprentic\w*", r"\b(new|fresh) grads?\b",
    r"\bgraduates?\b", r"\blearn(ing)? to code\b", r"\bexpertise\b",
]



HUMAN = (r"(humans?|persons?|interns?|juniors?|seniors?|employees?|workers?|staff|experts?|"
         r"professionals?|doctors?|lawyers?|accountants?|programmers?|developers?|devs|engineers?|"
         r"coders?|artists?|writers?|designers?|translators?|teachers?|nurses?|radiologists?|"
         r"assistants?|secretar(y|ies)|analysts?|(a |an )?(real |actual )?person|me)")
WORK_OBJECT = (r"(jobs?|tasks?|my job|my work|projects?|code|coding|programming|reports?|"
               r"emails?|spreadsheets?|analysis|translation|invoices?|diagnos\w*|legal|"
               r"accounting|customer service|support tickets?|clients?|customers?|production)")
CAPABILITY_STRONG = [
    r"\b(can|can't|cant|cannot|could|couldn't|will|won't|able to|unable to|capable of|incapable of|"
    r"good enough to|not good enough to|smart enough to|reliable enough to) (\w+ ){0,3}"
    r"(do|perform|handle|complete|automate|take over) (\w+ ){0,3}" + WORK_OBJECT + r"\b",
    r"\b(better|worse|faster|slower|cheaper|more accurate|less accurate|more reliable|"
    r"less reliable) than (a |an |the |most |any |average |real |human |junior |senior )?" + HUMAN + r"\b",
    r"\b(as good as|as bad as|outperforms?|replaces?) (a |an |the |most |any |average |real |human )?"
    r"(intern|junior|employee|worker|expert|professional|doctor|lawyer|programmer|developer|engineer)s?\b",
    r"\b" + HUMAN + r" (\w+ ){0,2}(also )?(hallucinate|make (\w+ )?mistakes|make things up|get (it|things) wrong)\b",
    r"\b(do|does|did|doing) (the )?(work|job) of (\w+ ){0,2}" + HUMAN + r"\b",
]
CAPABILITY_QUALITY = (r"\b(hallucinat\w*|mistakes?|errors?|bugs?|unreliable|reliab\w*|accura\w*|inaccura\w*|"
           r"(gets?|got|getting) (it|things|stuff) wrong|makes? (\w+ )?up)\b")
CAPABILITY_WORK_OBJECT = r"\b" + WORK_OBJECT + r"\b"

AUGMENTATION_STRONG = [
    r"\baugment(s|ed|ing|ation)? (\w+ ){0,2}(humans?|people|workers|employees|staff|jobs?|work|"
    r"us|me|developers|engineers|programmers|professionals|labou?r|teams?)\b",
    r"\b(replac\w*)\s*(or|/|and|vs\.?|rather than|not)\s*augment\w*\b",
    r"\baugment\w*\s*(or|/|and|vs\.?|rather than|not)\s*replac\w*\b",
    r"\b(copilot|co-pilot|assistant|sidekick|helper|partner|tool) (\w+ ){0,2}"
    r"(not|rather than|instead of|isn'?t|is not) (\w+ ){0,2}(a )?replac\w*\b",
    r"\bnot (\w+ ){0,2}(a )?replac\w* (\w+ ){0,3}(but|it'?s|just) (\w+ ){0,2}"
    r"(a |an )?(tool|assistant|copilot|co-pilot|aid|helper)\b",
    r"\bwork(s|ing)? (alongside|together with|hand in hand with) (humans|people|us|workers)\b",
    r"\breplaced by (\w+ ){0,3}(someone|people|humans|workers|developers|devs|engineers) "
    r"(who|that) (use|uses|know how to use|leverage)\b",
]
AUGMENTATION_WEAK = [
    r"\b(frees?|freed|freeing) (up )?(\w+ )?(time|me|us|people|workers|humans|staff|employees)\b",
    r"\b(boring|tedious|repetitive|menial|mundane|grunt|busy)[- ]?(tasks|work|jobs|stuff|parts)\b",
    r"\b(assist|assists|assisting|amplif\w*|empower\w*|enhanc\w*|complement\w*|supercharg\w*|"
    r"boost\w*) (\w+ ){0,2}(humans?|people|workers|employees|staff|developers|devs|engineers|"
    r"programmers|me|us|my|our|their|productivity|output|skills|work)\b",
]
AUGMENTATION_LOOP = r"\b(humans?|people)[- ]in[- ]the[- ]loop\b"
AUGMENTATION_TOOL = r"\b(just|only|merely|is|as|it'?s) (just |only |merely )?(a |an )?(tool|assistant|aid|copilot|co-pilot)\b"
AUGMENTATION_WORK_CONTEXT = (r"\b(jobs?|work|workers?|tasks?|productiv\w*|employees?|professionals?|"
                             r"developers?|programmers?|engineers?|coding|code|business|workflow|"
                             r"translat\w*|writing|design|doctors?|lawyers?|teachers?)\b")

TRANSFORMATION_STRONG = [
    r"\b(creat\w*|generat\w*|open\w* up|spawn\w*|bring|brings|brought) (\w+ ){0,2}(new )?"
    r"(jobs|roles|careers|job opportunities|industries|professions)\b",
    r"\bjob creation\b", r"\bnew (kinds? of |types? of )?(jobs|roles|careers|professions|occupations)\b",
    r"\b(jobs?|work|roles?|careers?|professions?|labou?r market|job market|workforce|workplace) "
    r"(will|would|is going to|are going to|gonna|has to|have to|must|need to|is|are) (\w+ )?"
    r"(chang|evolv|shift|transform|adapt|restructur)\w*\b",
    r"\b(chang|transform|reshap|redefin|restructur|revolutioni[sz])\w* (\w+ ){0,2}(how we work|"
    r"the way we work|the job market|the labou?r market|the workforce|the workplace|jobs|work|"
    r"careers|professions)\b",
    r"\b(won'?t|will not|wont|isn'?t going to|is not going to|not going to|doesn'?t|does not) "
    r"(\w+ ){0,2}(change|affect|impact|disrupt|transform) (\w+ ){0,3}(jobs?|work|employment|workers|"
    r"careers?|the job market|the labou?r market)\b",
]
TRANSFORMATION_WEAK = [
    r"\b(horses? (were|was|got) replaced|elevator operators?|switchboard operators?|typists?|"
    r"lamplighters?|bank tellers?|telephone operators?)\b",
]
TRANSFORMATION_ANALOGY = (r"\b(industrial revolution|luddites?|horse[- ]and[- ](buggy|carriage)|"
                          r"printing press|spinning jenny|tractors?|the loom|looms|cars? replaced)\b")
TRANSFORMATION_JOB_CONTEXT = (r"\b(jobs?|workers?|employment|unemploy\w*|labou?r|livelihoods?|"
                              r"careers?|professions?|occupations?|weavers|farmers|farm hands)\b")

CLAIM_TERMS = [
    r"\bhyp(e|ed|es|ing)\b", r"\boverhyp\w*", r"\bbubble\b",
    r"\boverpromis\w*", r"\boversold\b", r"\bgrift\w*", r"\bsnake oil\b",
    r"\bbs\b", r"\bbull ?shit\b", r"\blie(s|d)?\b", r"\blying\b",
    r"\bliars?\b", r"\bscam\w*", r"\bfraud\w*", r"\bcon\b", r"\bponzi\b",
    r"\binvest(or|ors|ment|ments)\b", r"\bvaluations?\b", r"\bprofit\w*",
    r"\brevenue\b", r"\bburn(ing)? (cash|money)\b", r"\bcrash\w*",
    r"\bdot[- ]?com\b", r"\bhallucinat\w*", r"\bsustainab\w*",
    r"\bcapex\b", r"\bnot profitable\b", r"\bunprofitable\b",
]

MENTION_PATTERN = re.compile(r"(?<![\w@])@[\w.\-]{2,}")
HASHTAG_PATTERN = re.compile(r"(?<![\w#])#\w+")
VIDEO_TIMESTAMP_PATTERN = re.compile(r"(?<![\d:])\d{1,2}:\d{2}(?::\d{2})?(?![\d:])")

MENTION_PLACEHOLDER = "[User]"
MENTION_REPLACE_PATTERN = re.compile(r"(?<!\w)@[\w.\-]+(?:@[\w.\-]+)*")
_TS = r"(?<![\d:.])\d{1,2}:\d{2}(?::\d{2})?(?!\d|:\d)(?!\s*(?:[ap]\.?m\b))"
_TS_RANGE = _TS + r"(?:\s*(?:-|–|—|~|to)\s*" + _TS + r")?"
VIDEO_TIMESTAMP_REMOVAL = re.compile(
    r"[(\[]\s*" + _TS_RANGE + r"\s*[)\]]" + r"|@?\s?" + _TS_RANGE, re.IGNORECASE)
INTENSIFIED_TAG = "[Intensified]"
CAPS_WORD_MIN_ZIPF = 3.0
CAPS_ACRONYM_SHARE = 0.5
CAPS_MIN_EVIDENCE = 3
ELONGATION_MIN_ZIPF = 2.0
ELONGATION_MIN_GAIN = 2.0    
WORD_TOKEN = re.compile(r"[^\W\d_]+(?:'[^\W\d_]+)?")
ELONGATED_RUN = re.compile(r"([^\W\d_])\1{2,}")
BOLD_PATTERN = re.compile(r"(?<![\w*])\*{1,2}(?=\S)([^*\n]+?)(?<=\S)\*{1,2}(?![\w*])")
ITALIC_PATTERN = re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])")
EMPTY_BRACKETS = re.compile(r"\(\s*[-–—~,:;]*\s*\)|\[\s*[-–—~,:;]*\s*\]")
SPACE_BEFORE_PUNCTUATION = re.compile(r"[ \t]+([.,!?;:)\]])")

FRAMES = {
    "replacement": {"strong": REPLACEMENT_STRONG, "weak": REPLACEMENT_WEAK,
                    "pairs": [], "requires_ai": False},
    "use_at_work": {"strong": USE_STRONG, "weak": USE_WEAK,
                    "pairs": [], "requires_ai": False},
    "skills": {"strong": SKILLS_STRONG, "weak": SKILLS_WEAK,
               "pairs": [], "requires_ai": False},
    "capability": {"strong": CAPABILITY_STRONG, "weak": [],
                   "pairs": [(CAPABILITY_QUALITY, CAPABILITY_WORK_OBJECT)],
                   "requires_ai": True},
    "augmentation": {"strong": AUGMENTATION_STRONG, "weak": AUGMENTATION_WEAK,
                     "pairs": [(AUGMENTATION_TOOL, AUGMENTATION_WORK_CONTEXT),
                               (AUGMENTATION_LOOP, AUGMENTATION_WORK_CONTEXT)],
                     "requires_ai": False},
    "transformation": {"strong": TRANSFORMATION_STRONG, "weak": TRANSFORMATION_WEAK,
                       "pairs": [(TRANSFORMATION_ANALOGY, TRANSFORMATION_JOB_CONTEXT)],
                       "requires_ai": False},
}