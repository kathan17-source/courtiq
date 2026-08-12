import { ROUTE_BY_ID, ROUTE_BY_PAGE, normalizeRoute, defaultRouteForProduct } from './js/router.js';
import { readJsonStore } from './js/storage.js';
import { createApiClient } from './js/api.js';

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

const ROSTERS = {
  men: [
    'Carlos Alcaraz', 'Jannik Sinner', 'Novak Djokovic', 'Alexander Zverev', 'Taylor Fritz',
    'Ben Shelton', 'Alex de Minaur', 'Jack Draper', 'Daniil Medvedev', 'Holger Rune',
    'Casper Ruud', 'Andrey Rublev', 'Stefanos Tsitsipas', 'Tommy Paul', 'Hubert Hurkacz',
    'Lorenzo Musetti', 'Frances Tiafoe', 'Grigor Dimitrov', 'Karen Khachanov',
    'Felix Auger-Aliassime', 'Matteo Berrettini', 'Sebastian Korda', 'Arthur Fils',
    'Jakub Mensik', 'Tomas Machac', 'Jiri Lehecka', 'Francisco Cerundolo', 'Flavio Cobolli',
    'Sebastian Baez', 'Ugo Humbert'
  ],
  women: [
    'Aryna Sabalenka', 'Iga Swiatek', 'Coco Gauff', 'Elena Rybakina', 'Jessica Pegula',
    'Jasmine Paolini', 'Qinwen Zheng', 'Mirra Andreeva', 'Barbora Krejcikova', 'Naomi Osaka',
    'Madison Keys', 'Emma Navarro', 'Belinda Bencic', 'Elina Svitolina', 'Daria Kasatkina',
    'Danielle Collins', 'Jelena Ostapenko', 'Victoria Azarenka', 'Sofia Kenin',
    'Leylah Fernandez', 'Emma Raducanu', 'Katie Boulter', 'Beatriz Haddad Maia',
    'Ekaterina Alexandrova', 'Liudmila Samsonova', 'Veronika Kudermetova', 'Elise Mertens',
    'Paula Badosa', 'Ons Jabeur', 'Karolina Muchova'
  ]
};

const GRAND_SLAMS = [
  { name: 'Australian Open', surface: 'Hard' },
  { name: 'Roland Garros', surface: 'Clay' },
  { name: 'Wimbledon', surface: 'Grass' },
  { name: 'US Open', surface: 'Hard' }
];

const DIRECTORY_PLAYERS = Array.isArray(window.COURTIQ_PLAYER_DIRECTORY) ? window.COURTIQ_PLAYER_DIRECTORY : [];
const DIRECTORY_BY_TOUR = {
  ATP: DIRECTORY_PLAYERS.filter(player => player.tour === 'ATP'),
  WTA: DIRECTORY_PLAYERS.filter(player => player.tour === 'WTA')
};
const ALL_PLAYERS = DIRECTORY_PLAYERS.length
  ? DIRECTORY_PLAYERS.map(player => player.name)
  : [...ROSTERS.men, ...ROSTERS.women];
const skillCache = new Map();

// CourtIQ v2 data contract:
// When production stats are available, inject them as window.COURTIQ_PLAYER_STATS
// or generate this object from work/backtest_courtiq_model.js.
// Until then, the predictor uses an explicitly labelled demo fallback so the
// app does not pretend local demo values are real historical tennis data.
const PLAYER_STATS = window.COURTIQ_PLAYER_STATS || {};
const API_BASE = window.COURTIQ_API_BASE
  || localStorage.cqApiBase
  || (location.protocol === 'http:' || location.protocol === 'https:' ? location.origin : 'http://127.0.0.1:8000');
const apiClient = createApiClient(API_BASE);
const DATA_STATUS = Object.keys(PLAYER_STATS).length
  ? {
    label: 'Historical data loaded',
    detail: `${Object.keys(PLAYER_STATS).length} player stat profiles available for the predictor.`,
    isDemo: false
  }
  : {
    label: 'Local preview mode',
    detail: 'Connect the prediction API for validated forecasts.',
    isDemo: true
  };

const TRAINING_BLOCKS = [
  {
    title: 'Explosive first step + split-step timing',
    target: 'Court speed and recovery after contact',
    how: 'Stand on the baseline, toss or rally one ball, split as the opponent would strike, push hard to the cone, shadow the hit, then recover behind the centre marker.',
    dose: '5 rounds × 45 seconds · 30 seconds rest',
    cue: 'Land wide, chest quiet, first step pushes from the outside leg.'
  },
  {
    title: 'Open-stance forehand power chain',
    target: 'Forehand heaviness without swinging only from the arm',
    how: 'Load the outside leg, coil shoulders, keep the non-hitting hand across the body, then rotate hips before the racket accelerates. Finish balanced.',
    dose: '4 sets × 8 shadow swings + 8 live balls',
    cue: 'If your chest opens before the bounce, you are early. If your arm pulls first, slow it down.'
  },
  {
    title: 'Backhand stability under pace',
    target: 'Two-wing consistency when rushed',
    how: 'Start one step behind baseline. Feed medium pace to the backhand, block the first two balls deep cross-court, then change direction only after a deep ball.',
    dose: '3 games to 11 points',
    cue: 'Unit turn before bounce, contact in front, recover before admiring the shot.'
  },
  {
    title: 'Serve leg drive + landing control',
    target: 'Free serve power and safer shoulder loading',
    how: 'Toss, load both legs, drive upward, contact at full reach, land inside court on the front foot, then take one recovery step.',
    dose: '5 × 8 serves: wide, body, T, repeat',
    cue: 'If the landing collapses left/right, reduce speed until the finish is quiet.'
  }
];

function learnLesson(id, title, concept, why, cues, mistake, drill, related = [], visual = '') {
  return { id, title, concept, why, cues, mistake, drill, related, visual };
}

const LEARN_CURRICULUM = {
  Beginner: [
    { id: 'foundations', title: 'Foundations', lessons: [
      learnLesson('ready-position', 'Ready position', 'A balanced base that lets you move in any direction before the opponent strikes.', 'Starting neutral reduces the extra steps needed to reach the next ball.', ['Feet just wider than hips', 'Weight on the front of the feet', 'Racket supported in front'], 'Standing tall with the racket hanging beside the body.', 'Partner points left or right after a split step. Push to that side and recover; 3 × 45 seconds.', ['split-step', 'court-zones']),
      learnLesson('court-positioning', 'Basic court positioning', 'Position relative to the baseline should reflect the ball you just hit and the time available.', 'Good positioning protects space without forcing a rushed first step.', ['Recover after every shot', 'Move diagonally after wide balls', 'Respect short balls by moving forward'], 'Returning to the centre mark regardless of shot geometry.', 'Rally cross-court and freeze after each recovery to check your position.', ['court-zones', 'recovery-position'], 'recovery'),
      learnLesson('tennis-scoring', 'Tennis scoring', 'Games progress 0, 15, 30, 40; deuce requires two consecutive points.', 'Knowing the score clarifies risk and prevents avoidable confusion.', ['Call the score before serving', 'Server score is called first', 'Change ends after odd-numbered games'], 'Playing the next point without confirming disputed score.', 'Play a first-to-four mini game using full tennis scoring.', []),
      learnLesson('court-zones', 'Court zones', 'Baseline, neutral, transition and net zones create different shot priorities.', 'Recognising the zone helps you choose margin before speed.', ['Deep ball: stabilise', 'Short ball: move through it', 'Net zone: finish or force a weak reply'], 'Trying to attack from well behind the baseline.', 'Coach calls a zone; move there and name a high-margin target.', ['court-positioning', 'neutral-placement'], 'net')
    ]},
    { id: 'groundstrokes', title: 'Groundstrokes', lessons: [
      learnLesson('forehand-grip', 'Forehand grip', 'A consistent grip supports a repeatable racket face and comfortable contact.', 'Consistency matters more than copying one professional grip.', ['Find the same bevel each time', 'Keep the hand relaxed', 'Match grip to intended swing'], 'Changing grip during the forward swing.', 'Reset the racket between ten shadow swings, checking the grip before each turn.', ['unit-turn', 'contact-in-front']),
      learnLesson('backhand-setup', 'Backhand grip and setup', 'Set the hands and shoulder turn together before the bounce.', 'Early organisation creates time for either a one- or two-handed backhand.', ['Turn both shoulders', 'Set the grip during the turn', 'Create space from the ball'], 'Waiting for the bounce before preparing.', 'Shadow ten backhands, calling “turn” before an imagined bounce.', ['unit-turn', 'balanced-finish']),
      learnLesson('unit-turn', 'Unit turn', 'The shoulders and racket organise as one unit before the forward swing.', 'Preparation before the bounce reduces rushed arm action.', ['Read the ball early', 'Turn shoulders, not only hands', 'Keep the head level'], 'Taking the racket back with the arm while the chest stays facing forward.', 'Five slow unit turns, then 3 × 8 cross-court balls prepared before the bounce.', ['contact-in-front', 'swing-path']),
      learnLesson('contact-in-front', 'Contact in front', 'The preferred contact window sits slightly in front of the lead hip.', 'That spacing supports control, extension and a balanced recovery.', ['Create room with the feet', 'Meet the ball in front', 'Keep the head steady'], 'Letting the ball crowd the body and striking beside the hip.', 'Drop-feed 3 × 10 balls and hold the finish long enough to check spacing.', ['unit-turn', 'balanced-finish'], 'contact'),
      learnLesson('swing-path', 'Swing path', 'The racket travels through the ball with enough low-to-high shape for safe net clearance.', 'A repeatable path creates height and depth without forcing pace.', ['Swing through before wrapping', 'Finish in balance', 'Keep the racket face controlled'], 'Brushing sharply up without driving through the contact zone.', 'Hit 3 × 8 balls over a safe net-height window to a deep target.', ['contact-in-front', 'balanced-finish']),
      learnLesson('balanced-finish', 'Balanced finish', 'A useful finish leaves the body organised for the next movement.', 'Balance makes recovery faster and exposes swing-path errors.', ['Finish on a stable base', 'Chest stays controlled', 'Recover before watching the shot'], 'Falling sideways after contact.', 'Hit and freeze for two seconds on ten controlled balls, then add recovery.', ['swing-path', 'recovery-position'])
    ]},
    { id: 'serve', title: 'Serve', lessons: [
      learnLesson('continental-grip', 'Continental serve grip', 'The continental grip supports pronation, spin and a versatile racket face.', 'It creates a safer path toward a complete serve than a forehand-style grip.', ['Hold the racket like a hammer', 'Keep the hand relaxed', 'Lead upward with the edge'], 'Sliding toward a forehand grip to push the ball in.', 'Serve from the service line with a continental grip; 3 × 8 smooth contacts.', ['toss-fundamentals', 'serve-contact']),
      learnLesson('toss-fundamentals', 'Toss fundamentals', 'A controlled toss places the ball inside a repeatable hitting window.', 'A stable toss lets the motion continue upward without chasing the ball.', ['Release rather than flick', 'Quiet tossing arm', 'Let a poor toss drop'], 'Throwing the toss with wrist spin.', 'Place a racket on court as a landing target; make 7 of 10 tosses land nearby.', ['trophy-position', 'serve-contact']),
      learnLesson('trophy-position', 'Trophy and loading position', 'The legs and trunk load while the tossing arm extends and the racket prepares to accelerate.', 'A coordinated load stores energy without pausing rigidly.', ['Stay tall through the toss', 'Load smoothly', 'Keep shoulders tilted'], 'Forcing a frozen pose and losing rhythm.', 'Shadow 3 × 8 continuous serve motions at half speed.', ['toss-fundamentals', 'serve-contact']),
      learnLesson('serve-contact', 'Serve contact', 'Contact occurs at full comfortable reach with upward intent.', 'Reaching high improves net clearance and lets the racket accelerate naturally.', ['Drive up to contact', 'Eyes track the toss', 'Reach without collapsing sideways'], 'Pulling the toss down by dropping the head early.', 'Serve 4 × 6 at 60% pace, scoring only balanced full-reach contacts.', ['trophy-position', 'serve-landing']),
      learnLesson('serve-landing', 'Landing and balance', 'The serve finishes with controlled forward momentum and a stable first recovery step.', 'A balanced landing prepares the player for the return.', ['Land inside the court', 'Control the trunk', 'Recover behind the first ball'], 'Landing sideways and staying fixed after the serve.', 'Serve, land, and split on a partner clap; 3 × 8 repetitions.', ['serve-contact', 'serve-first-ball'])
    ]},
    { id: 'movement', title: 'Movement', lessons: [
      learnLesson('split-step', 'Split step', 'A small timed hop loads both legs as the opponent strikes.', 'Landing at contact helps the first move react to the actual ball.', ['Time the landing to contact', 'Land wide and quiet', 'Push, do not reach'], 'Jumping too early and becoming flat-footed before contact.', 'Partner feeds randomly after each split; 4 × 30 seconds.', ['ready-position', 'side-shuffle']),
      learnLesson('side-shuffle', 'Side shuffle', 'Adjustment steps preserve a neutral orientation over short lateral distances.', 'They help fine-tune spacing without crossing the feet unnecessarily.', ['Stay low', 'Feet do not click together', 'Use for short recoveries'], 'Using long crossing steps when only a small adjustment is needed.', 'Shuffle between two cones, split, shadow swing, and return; 3 × 45 seconds.', ['split-step', 'crossover-recovery']),
      learnLesson('crossover-recovery', 'Crossover recovery', 'A crossover step covers more ground after a wide ball or lob.', 'It is more efficient than shuffling across a large distance.', ['Turn toward the destination', 'Cross over for distance', 'Use adjustment steps near the ball'], 'Backpedalling or shuffling when the court distance is large.', 'Recover from doubles alley to centre using one crossover then adjustment steps.', ['side-shuffle', 'recovery-position'], 'recovery'),
      learnLesson('recovery-position', 'Recover to the right position', 'Recovery depends on the direction and quality of the shot just played.', 'The correct bisector protects the opponent’s most realistic replies.', ['Recover relative to shot angle', 'Deep buys more time', 'Wide replies require diagonal recovery'], 'Running automatically to the geometric centre.', 'Play cooperative points and call the protected lane after each shot.', ['court-positioning', 'crossover-recovery'], 'recovery')
    ]},
    { id: 'patterns', title: 'First patterns', lessons: [
      learnLesson('cross-court-consistency', 'Cross-court consistency', 'Cross-court offers more court length and a lower net.', 'That margin makes it the foundation of neutral rally construction.', ['Aim well inside the lines', 'Build height and depth', 'Change direction from balance'], 'Trying to finish neutral balls down the line.', 'Reach 12 cross-court balls as a pair before changing direction.', ['neutral-placement', 'serve-first-ball']),
      learnLesson('serve-first-ball', 'Serve and first ball', 'The serve begins a two-shot pattern rather than ending the point by itself.', 'Planning the next ball improves recovery and target clarity.', ['Recover immediately after serving', 'Expect the common return', 'Use a large first-ball target'], 'Watching the serve instead of preparing for the return.', 'Serve to one location and play the next ball cross-court; 4 × 6.', ['serve-landing', 'neutral-placement']),
      learnLesson('return-first-ball', 'Return and first ball', 'A controlled return starts the point and prepares a stable next position.', 'Depth and recovery matter before aggressive placement.', ['Compact preparation', 'Aim through the middle third', 'Recover after contact'], 'Swinging bigger because the serve arrives faster.', 'Block 3 × 8 returns deep middle, then play one neutral ball.', ['neutral-placement', 'cross-court-consistency']),
      learnLesson('neutral-placement', 'Neutral-ball placement', 'A neutral ball prioritises depth and margin over immediate attack.', 'It prevents low-percentage errors while waiting for a shorter ball.', ['Deep middle is reliable', 'Cross-court creates margin', 'Attack only from balance'], 'Treating every rally ball as an attacking opportunity.', 'Play to two large deep targets; point counts only after three neutral balls.', ['cross-court-consistency', 'court-zones'])
    ]}
  ],
  Intermediate: [
    { id: 'serve-development', title: 'Serve development', lessons: [
      learnLesson('serve-shapes', 'Flat, slice and kick concepts', 'Different racket paths change pace, curve and bounce.', 'A reliable second shape makes location and intent less predictable.', ['Flat for direct pace', 'Slice curves away or into the body', 'Kick prioritises net clearance and bounce'], 'Chasing spin by slowing the arm dramatically.', 'Serve four of each shape to one large target at controlled pace.', ['serve-placement', 'second-serve-intention']),
      learnLesson('serve-placement', 'Wide, body and T placement', 'Three locations move the returner and change the likely return lane.', 'Location can create a predictable first ball without maximum speed.', ['Use the same preparation', 'Body serves restrict extension', 'Recover for the likely reply'], 'Aiming at lines instead of useful target zones.', 'Play sets of six: two wide, two body, two T; score location before pace.', ['serve-plus-one', 'serve-shapes'], 'net'),
      learnLesson('second-serve-intention', 'First vs second serve intention', 'First serves can press advantage; second serves must combine safety with enough shape to avoid attack.', 'Clear intention reduces tentative deceleration.', ['Choose location before the toss', 'Keep second-serve racket speed', 'Build margin with shape'], 'Guiding the second serve with a slow arm.', 'Alternate first- and second-serve targets for 5 × 6 balls.', ['serve-shapes', 'serve-plus-one']),
      learnLesson('serve-plus-one', 'Serve +1 patterns', 'Serve location and recovery position set the geometry of the next shot.', 'The first ball should exploit the response the serve was designed to produce.', ['Name the expected return lane', 'Recover before attacking', 'Use inside-out only when spacing allows'], 'Choosing the +1 target after the return has already bounced.', 'Serve to one location and play +1 to a preselected large target; 4 × 6.', ['serve-placement', 'inside-out-forehand'], 'net')
    ]},
    { id: 'return', title: 'Return', lessons: [
      learnLesson('return-positioning', 'Return positioning', 'Distance and lateral position adjust time, contact height and available angles.', 'A deliberate starting spot matches the server’s pace and location patterns.', ['Start where contact is comfortable', 'Move with the toss', 'Adjust between first and second serve'], 'Standing in one position against every server.', 'Return ten serves from three depths and note the cleanest contact zone.', ['compact-return', 'attack-second-serve'], 'contact'),
      learnLesson('compact-return', 'Compact return', 'A short preparation redirects pace with stable contact.', 'Less backswing protects timing against faster serves.', ['Turn with the shoulders', 'Quiet hands', 'Finish through the target'], 'Taking a full rally swing against pace.', 'Partner serves at 70%; block 4 × 6 returns beyond the service line.', ['block-big-serves', 'return-plus-one']),
      learnLesson('block-big-serves', 'Blocking big serves', 'A stable racket face uses incoming speed to send the ball deep.', 'Neutral depth is often more valuable than forcing an attacking return.', ['Firm structure, relaxed grip', 'Meet the ball early', 'Large deep-middle target'], 'Trying to manufacture extra pace under time pressure.', 'Return 3 × 8 first serves; score one point for every ball beyond service line.', ['compact-return', 'return-plus-one']),
      learnLesson('attack-second-serve', 'Attacking second serves', 'Extra time permits forward court position and controlled initiative.', 'Taking the ball earlier can reduce the server’s recovery time.', ['Step in before the bounce', 'Use a clear target', 'Attack with shape, not only speed'], 'Overhitting because the serve looks slow.', 'Start inside the baseline and return 4 × 6 to a large cross-court target.', ['return-positioning', 'return-plus-one']),
      learnLesson('return-plus-one', 'Return +1', 'The return target should prepare the next rally ball and recovery position.', 'A two-shot plan prevents the return from becoming an isolated swing.', ['Recover off the return', 'Expect the server’s strongest +1', 'Stabilise before changing direction'], 'Admiring an aggressive return and losing the next ball.', 'Return, recover, and play one cross-court ball; 4 × 5 live sequences.', ['compact-return', 'cross-court-tolerance'])
    ]},
    { id: 'rally-patterns', title: 'Groundstroke patterns', lessons: [
      learnLesson('cross-court-tolerance', 'Cross-court tolerance', 'Sustained height, depth and spacing create pressure without shrinking the target.', 'Tolerance earns shorter balls and reduces donated errors.', ['Reset spacing each ball', 'Clear the net safely', 'Hold direction under neutral pressure'], 'Changing direction because the rally feels long.', 'Play cross-court to 15; an error before eight balls loses two points.', ['safe-direction-change', 'short-ball-recognition']),
      learnLesson('safe-direction-change', 'Changing direction safely', 'Direction changes are strongest from balance and on a ball that does not force late contact.', 'The line change has less court length and usually a higher net.', ['Change from inside the court', 'Meet the ball in front', 'Recover for the new angle'], 'Redirecting a deep, wide ball while stretched.', 'Rally cross-court; change only after a ball lands short of a marked line.', ['cross-court-tolerance', 'short-ball-recognition'], 'contact'),
      learnLesson('inside-out-forehand', 'Inside-out forehand', 'Moving around the backhand can use the forehand to pressure the opponent’s backhand corner.', 'It creates a repeatable pattern while preserving cross-court margin.', ['Move early around the ball', 'Leave recovery space', 'Do not expose the line without pressure'], 'Running too far around and hitting while falling away.', 'Feed to backhand half; hit 3 × 8 inside-out forehands and recover.', ['inside-in-forehand', 'backhand-construction']),
      learnLesson('inside-in-forehand', 'Inside-in forehand', 'The inside-in change exploits space after the opponent shades toward the cross-court pattern.', 'It is effective when court position and contact are clearly favourable.', ['Build the inside-out first', 'Change from balance', 'Recover for the open cross-court reply'], 'Using inside-in as the first ball of the pattern.', 'Play two inside-out balls before one controlled inside-in; repeat ten times.', ['inside-out-forehand', 'safe-direction-change']),
      learnLesson('backhand-construction', 'Backhand pattern construction', 'Depth cross-court stabilises the backhand exchange before a selective change.', 'A dependable pattern protects the wing without becoming passive.', ['Hold cross-court depth', 'Use height under pressure', 'Change only from a strong base'], 'Forcing down-the-line contact from behind the body.', 'Play backhand cross-court; earn permission to change after three deep balls.', ['cross-court-tolerance', 'safe-direction-change']),
      learnLesson('short-ball-recognition', 'Short-ball recognition', 'A shorter bounce and more available time signal movement into the court.', 'Early recognition supports a better contact point and target choice.', ['Read depth before bounce', 'Move through the shot', 'Choose approach or controlled attack'], 'Waiting behind the baseline for a short ball to arrive.', 'Coach mixes deep and short feeds; call “in” before the bounce and attack only short balls.', ['approach-selection', 'defense-to-offense'])
    ]},
    { id: 'transition', title: 'Defense and transition', lessons: [
      learnLesson('neutralize-stretched', 'Neutralising when stretched', 'Height, depth and middle targets buy recovery time when balance is compromised.', 'Defense succeeds by reducing the opponent’s immediate options.', ['Create net clearance', 'Use the middle when late', 'Recover before counterattacking'], 'Attempting a winner from outside the singles line.', 'Feed wide; recover each ball deep middle before playing the point out.', ['recovery-geometry', 'defense-to-offense']),
      learnLesson('recovery-geometry', 'Recovery geometry', 'The ideal recovery point bisects the opponent’s likely angles rather than the whole court.', 'Shot direction changes which space must be protected first.', ['Recover diagonally from wide positions', 'Depth changes available time', 'Split as the opponent strikes'], 'Returning to the centre mark after every ball.', 'Hit alternately cross-court and down the line, then freeze at the correct bisector.', ['neutralize-stretched', 'defense-to-offense'], 'recovery'),
      learnLesson('defense-to-offense', 'Defense-to-offense transition', 'A neutralising ball can restore position before the next short reply is attacked.', 'Trying to reverse the point too early often compounds poor balance.', ['Defend high and deep', 'Rebuild court position', 'Attack the first genuinely short ball'], 'Turning the first reachable ball into a low-margin attack.', 'Start stretched; point becomes live only after one deep neutral ball.', ['neutralize-stretched', 'short-ball-recognition']),
      learnLesson('approach-selection', 'Approach-shot selection', 'Approach direction should limit the opponent’s best passing angle and support the first volley.', 'A good approach is measured by the next volley, not only its pace.', ['Approach from inside the court', 'Prefer depth and direction', 'Close behind the shot'], 'Approaching down the middle without a coverage plan.', 'Feed short balls; approach to a target and play one live volley.', ['first-volley', 'short-ball-recognition'], 'net'),
      learnLesson('first-volley', 'First volley', 'The first volley often controls depth and position before the finish.', 'A stable first volley keeps the opponent defending and allows a better close.', ['Split before contact', 'Volley through a large target', 'Close after the shot'], 'Trying to end the point with a difficult low first volley.', 'Approach and play the first volley deep; second volley is live.', ['approach-selection', 'recovery-geometry'])
    ]},
    { id: 'match-tactics', title: 'Match tactics', lessons: [
      learnLesson('high-margin-targets', 'High-margin targets', 'Targets several feet inside the lines preserve pressure while reducing error risk.', 'Reliable location matters more than occasional line painting.', ['Use depth before width', 'Shrink targets under pressure', 'Earn the short ball'], 'Confusing aggressive intent with aiming closer to lines.', 'Play points where winners count only if the previous ball landed in a large target.', ['protect-weakness', 'pressure-patterns']),
      learnLesson('protect-weakness', 'Protecting a weakness', 'Patterns can reduce exposure of a weaker wing without avoiding it completely.', 'Good protection buys time and creates more predictable exchanges.', ['Use depth through the middle', 'Run around only with space', 'Recover for the exposed lane'], 'Over-protecting and leaving obvious open court.', 'Play half-court points starting on the weaker wing; neutralise before attacking.', ['high-margin-targets', 'inside-out-forehand']),
      learnLesson('pressure-patterns', 'Patterns at 30–30 and deuce', 'Pressure points reward a trusted pattern with a clear first target.', 'Pre-commitment reduces rushed tactical decisions while preserving adaptability.', ['Choose the pattern before play', 'Use your reliable serve or return', 'Keep the first target large'], 'Attempting a new low-percentage play because the score feels important.', 'Play ten 30–30 games using one declared opening pattern.', ['high-margin-targets', 'serve-plus-one']),
      learnLesson('vs-big-server', 'Playing a big server', 'Return position, compact preparation and neutral depth reduce the server’s first-strike advantage.', 'The aim is to start more neutral rallies, not win every return outright.', ['Read patterns between points', 'Block to a large target', 'Move on predictable second serves'], 'Trying to match serve pace with return pace.', 'Play return games where any deep neutral return earns a bonus point.', ['block-big-serves', 'attack-second-serve']),
      learnLesson('vs-defender', 'Playing a defensive player', 'Depth, selective angles and patient transition stop a defender from feeding on rushed errors.', 'Court position should improve before the target becomes smaller.', ['Build with depth', 'Use the short ball to move forward', 'Finish through position'], 'Going for a winner from the first neutral ball.', 'Point must include three deep balls before an attacking target is allowed.', ['short-ball-recognition', 'approach-selection'])
    ]}
  ],
  Advanced: [
    { id: 'serve-architecture', title: 'Serve architecture', lessons: [
      learnLesson('serve-sequences', 'Serve location sequences', 'Locations work as sequences that shape the returner’s expectation and court position.', 'A previous serve can make the next location more effective without increasing pace.', ['Track returner movement', 'Repeat until they adjust', 'Use contrast deliberately'], 'Randomising locations without learning from the return.', 'Play service games with a written three-serve sequence and record return contact.', ['serve-disguise', 'body-serve']),
      learnLesson('serve-disguise', 'Serve disguise', 'Similar toss and preparation delay the returner’s read of location or shape.', 'Late information reduces the returner’s ability to move early.', ['Keep early motion consistent', 'Change with racket path, not obvious setup', 'Accept a small pace tradeoff for accuracy'], 'Altering toss position so clearly that location is announced.', 'Film sets of wide and T serves; compare preparation up to racket drop.', ['serve-sequences', 'adaptive-serve-patterns']),
      learnLesson('body-serve', 'Body serve usage', 'The body serve limits extension and can jam aggressive return positions.', 'It changes the returner’s spacing and opens the next serve location.', ['Aim at the moving hip', 'Use against forward return positions', 'Plan the likely short reply'], 'Treating body as a miss between wide and T.', 'Serve 4 × 6 body balls and play the first ball behind the returner.', ['serve-sequences', 'serve-plus-one-geometry']),
      learnLesson('serve-plus-one-geometry', 'Serve +1 geometry', 'Serve direction alters recovery location, reply probability and available forehand space.', 'The +1 target should exploit the return lane created by the serve.', ['Map likely reply before serving', 'Recover on the correct angle', 'Take forehands only when the line remains protected'], 'Using the same +1 pattern after every serve location.', 'Play three location-specific serve +1 patterns for six repetitions each.', ['body-serve', 'adaptive-serve-patterns'], 'net'),
      learnLesson('second-serve-balance', 'Second-serve aggression vs safety', 'Second-serve quality balances shape, location and acceptable double-fault risk by score and opponent.', 'Passive placement can concede initiative even when it lands in.', ['Preserve racket speed', 'Use shape for margin', 'Adjust location risk by scoreboard'], 'Equating safety with deceleration.', 'Play ten-point service sets with declared conservative and assertive second-serve targets.', ['serve-sequences', 'pressure-serving']),
      learnLesson('adaptive-serve-patterns', 'Adapting to return position', 'Return depth and lateral bias reveal which serve spaces are expanding or shrinking.', 'The serve plan should respond to positioning rather than repeat mechanically.', ['Check position before the toss', 'Move the returner before chasing aces', 'Reassess after two similar returns'], 'Following the planned sequence after the returner has clearly adjusted.', 'Partner changes return position every two serves; name and execute the adjustment.', ['serve-sequences', 'serve-plus-one-geometry'])
    ]},
    { id: 'return-architecture', title: 'Return architecture', lessons: [
      learnLesson('return-depth-angle', 'Return depth vs angle', 'Depth removes time; angle moves the server but can expose court and increase error risk.', 'The right return depends on serve quality and your contact position.', ['Use depth from compromised contact', 'Create angle from inside the court', 'Recover for the geometry you create'], 'Forcing angle from a stretched return position.', 'Alternate deep-middle and angled returns from matched feeds; play the next ball.', ['return-position-change', 'first-strike-return'], 'net'),
      learnLesson('return-position-change', 'Changing return position', 'Moving forward, back or laterally changes time, bounce height and server target perception.', 'Visible variation can disrupt serving patterns and improve contact quality.', ['Change with a tactical reason', 'Move before the server starts', 'Keep the swing matched to available time'], 'Drifting positions without adjusting preparation length.', 'Return one game from three depths and chart clean-contact rate.', ['return-depth-angle', 'elite-first-serve']),
      learnLesson('first-strike-return', 'First-strike return patterns', 'An assertive return can preselect the server’s next contact and create the first attacking ball.', 'Placement plus recovery produces more value than raw return speed.', ['Attack predictable locations', 'Use a large directional target', 'Recover inside the baseline when earned'], 'Hitting hard without a plan for the server’s next ball.', 'Attack second serves to one target and play the next ball to the open court.', ['predictable-seconds', 'return-depth-angle']),
      learnLesson('elite-first-serve', 'Neutralising elite first serves', 'Compact redirection, adjusted depth and pattern reads increase the number of viable rally starts.', 'Against high pace, quality often means neutral depth rather than initiative.', ['Read toss and tendencies', 'Shorten the swing', 'Prioritise the central third'], 'Judging every non-attacking return as a failure.', 'Score returns: two points deep middle, one point in play, zero missed.', ['return-position-change', 'predictable-seconds']),
      learnLesson('predictable-seconds', 'Attacking predictable second serves', 'Repeated shape or location allows earlier movement and a more aggressive contact point.', 'Recognition turns server predictability into controlled first-strike pressure.', ['Confirm the pattern before moving', 'Take the ball earlier', 'Attack a space, not a line'], 'Guessing after only one example and exposing the return court.', 'Partner serves a repeated pattern with occasional change; attack only confirmed reads.', ['first-strike-return', 'return-position-change'])
    ]},
    { id: 'rally-construction', title: 'Rally construction', lessons: [
      learnLesson('court-asymmetry', 'Creating court asymmetry', 'Repeated pressure to one space shifts the opponent before the change goes elsewhere.', 'The opening is created before it is attacked.', ['Move the opponent beyond neutral', 'Hold the pattern long enough', 'Change from a strong contact'], 'Changing direction before the opponent’s recovery position moves.', 'Play two balls to one third, then one to the opposite third; repeat live.', ['open-space-first', 'pattern-tolerance'], 'net'),
      learnLesson('open-space-first', 'Opening space before changing direction', 'Depth and angle stretch recovery geometry before a directional change.', 'A change is higher quality when the opponent cannot recover through the middle.', ['Pressure with the first ball', 'Read opponent balance', 'Change behind or away intentionally'], 'Seeing open court without accounting for opponent momentum.', 'Rally cross-court until partner crosses a cone; then choose behind or open space.', ['court-asymmetry', 'depth-angle-tradeoff']),
      learnLesson('pattern-tolerance', 'Pattern tolerance', 'Competitive patterns require enough repetition to withstand neutral pressure.', 'Abandoning a sound pattern early often creates the opponent’s opportunity.', ['Separate discomfort from danger', 'Maintain depth under fatigue', 'Change only on a better ball'], 'Treating rally length itself as a reason to attack.', 'Play pattern points where direction cannot change before ball six.', ['court-asymmetry', 'absorbing-pace']),
      learnLesson('depth-angle-tradeoff', 'Depth vs angle tradeoffs', 'Depth limits time while angle opens court; combining both aggressively also increases risk.', 'Choosing the dominant objective clarifies target size and recovery.', ['Deep targets are larger', 'Angles require better court position', 'Recover for the space you open'], 'Trying for maximum depth and angle on the same neutral ball.', 'Alternate depth-only and angle-only pattern games, then choose live.', ['open-space-first', 'taking-time']),
      learnLesson('taking-time', 'Taking time away', 'Earlier contact reduces opponent recovery time but shrinks your preparation window.', 'Moving inside the baseline is valuable only when spacing remains organised.', ['Move on the opponent’s weaker depth', 'Shorten preparation', 'Hold court after contact'], 'Standing forward while contacting late.', 'Take alternating balls on the rise and at peak; chart depth and balance.', ['depth-angle-tradeoff', 'absorbing-pace'], 'contact'),
      learnLesson('absorbing-pace', 'Absorbing pace', 'Stable structure and controlled swing length redirect speed without fighting it.', 'This neutralises powerful opponents and preserves court position.', ['Set the racket early', 'Quiet the acceleration', 'Use the opponent’s pace to reach depth'], 'Adding a full acceleration to an already fast incoming ball.', 'Partner drives at 75%; block 20 balls beyond a deep target line.', ['taking-time', 'pattern-tolerance'])
    ]},
    { id: 'court-management', title: 'Court-position management', lessons: [
      learnLesson('baseline-positioning', 'Baseline positioning', 'Depth behind or inside the baseline should reflect opponent pace, bounce and your intention.', 'Small position changes alter contact height and time on both sides of the rally.', ['Adjust during the point', 'Step in on weak depth', 'Yield space when bounce demands it'], 'Holding one baseline depth regardless of ball quality.', 'Play points with a visible depth band; move forward only after short depth.', ['geometry-recovery', 'closing-court']),
      learnLesson('geometry-recovery', 'Recovery from shot geometry', 'Recovery location follows the angles created by your shot, not a fixed centre landmark.', 'Correct positioning closes the opponent’s most likely high-value replies.', ['Track your outgoing angle', 'Recover less after deep middle', 'Use diagonal paths after wide balls'], 'Over-recovering and opening the line behind the movement.', 'Freeze after each patterned ball and have a coach score the recovery spot.', ['baseline-positioning', 'closing-court'], 'recovery'),
      learnLesson('closing-court', 'Closing court intelligently', 'Moving forward is strongest when the opponent is stretched, late or forced to lift.', 'Court closure should follow evidence of a weak reply.', ['Read balance, not hope', 'Close along the shot line', 'Split before the reply'], 'Charging forward after a neutral approach.', 'Play approach points; move through the service line only after a visibly weak reply.', ['transition-decisions', 'geometry-recovery'], 'net'),
      learnLesson('transition-decisions', 'Transition decision-making', 'Approach, hold or retreat decisions depend on contact quality and opponent balance.', 'A flexible transition prevents being stranded in low-value court positions.', ['Approach behind quality', 'Hold when reply remains uncertain', 'Reset when contact breaks down'], 'Continuing forward because the original plan said to approach.', 'Mixed feeds: call approach, hold or reset before the ball crosses the net.', ['closing-court', 'geometry-recovery'])
    ]},
    { id: 'matchup-pressure', title: 'Matchups and pressure', lessons: [
      learnLesson('lefty-geometry', 'Lefty vs righty geometry', 'Cross-court forehands and serves naturally pressure different wings in opposite-handed matchups.', 'Understanding the default geometry helps protect the backhand corner and plan first strikes.', ['Track ad-court serve patterns', 'Protect the backhand exchange', 'Use forehand direction deliberately'], 'Applying same-handed patterns without adjusting court bias.', 'Play ad-court serve +1 points with one left-handed pattern and one counter-pattern.', ['matchup-archetypes', 'serve-sequences']),
      learnLesson('matchup-archetypes', 'Opponent archetype plans', 'Aggressive baseliners, counterpunchers, net rushers, big servers and heavy-spin players reward different margins and positions.', 'A plan should target a repeatable vulnerability without caricaturing the opponent.', ['Identify one real tendency', 'Choose one opening pattern', 'Update from match evidence'], 'Changing the entire game after one lost point.', 'Play four-point blocks against a declared style; adjust one variable after each block.', ['lefty-geometry', 'scoreboard-risk']),
      learnLesson('scoreboard-risk', 'Scoreboard-aware risk', 'The value of margin, surprise and first-strike aggression shifts with score and serve context.', 'Risk should change through target and pattern selection, not emotional swing speed.', ['Know the score before choosing', 'Protect reliable patterns under pressure', 'Use surprise selectively'], 'Aiming closer to lines simply because the point is important.', 'Play points from 15–40, 40–15 and deuce with a declared risk plan.', ['break-point-patterns', 'tiebreak-construction']),
      learnLesson('break-point-patterns', 'Break-point patterns', 'Return and serve choices on break points should lean on evidence-backed patterns and clear recovery positions.', 'A rehearsed start protects decision quality under pressure.', ['Choose one high-confidence opening', 'Expect the opponent’s trusted pattern', 'Stay adaptable after the first two shots'], 'Trying to win the entire game with one spectacular point.', 'Play ten break points using one serve plan and one return plan; chart first two shots.', ['scoreboard-risk', 'pressure-serving']),
      learnLesson('pressure-serving', 'Serving out sets', 'Serving with a lead rewards routine, location clarity and commitment to the next ball.', 'Attention on process prevents the scoreboard from speeding up the motion.', ['Keep the same between-point routine', 'Name serve and +1 target', 'Reset fully after each point'], 'Rushing after a missed first serve or lost point.', 'Start six service games at 30–15 and execute a written two-shot plan.', ['break-point-patterns', 'second-serve-balance']),
      learnLesson('tiebreak-construction', 'Tiebreak construction', 'Tiebreaks magnify mini-breaks, serve order and the value of stable opening patterns.', 'Point-by-point planning controls risk without becoming passive.', ['Track serve order', 'Use reliable patterns early', 'Reassess at changeovers'], 'Treating every tiebreak point as sudden death.', 'Play three tiebreaks and record the planned and actual first two shots of each point.', ['scoreboard-risk', 'pressure-serving'])
    ]}
  ]
};

const PUZZLE_CATEGORIES = ['Serve +1', 'Return', 'Defense', 'Attack', 'Pressure', 'Net Play', 'Surface Patterns'];
const PUZZLE_DIFFICULTIES = ['Beginner', 'Intermediate', 'Advanced', 'Elite'];
const PUZZLE_SURFACES = ['Hard court', 'Clay court', 'Grass court'];
const PUZZLE_ARCHETYPES = ['heavy topspin lefty', 'big server', 'counterpuncher', 'serve-and-volleyer', 'flat ball-striker', 'all-court mover'];

const PUZZLE_SCENARIO_SPACE_ESTIMATE =
  PUZZLE_CATEGORIES.length * PUZZLE_DIFFICULTIES.length * PUZZLE_SURFACES.length * PUZZLE_ARCHETYPES.length * 4 * 4 * 4 * 3 * 3 * 5 * 6;

function seededRandom(seed) {
  let value = Math.abs(Number(seed) || 1) % 2147483647;
  return () => {
    value = value * 16807 % 2147483647;
    return (value - 1) / 2147483646;
  };
}

function pickSeeded(list, random) {
  return list[Math.floor(random() * list.length) % list.length];
}

function tacticalStateFromSeed(seed, filters = {}) {
  const random = seededRandom(seed);
  const category = filters.category && filters.category !== 'Random' ? filters.category : pickSeeded(PUZZLE_CATEGORIES, random);
  const difficulty = filters.difficulty && filters.difficulty !== 'Any difficulty' ? filters.difficulty : pickSeeded(PUZZLE_DIFFICULTIES, random);
  const surface = filters.surface && filters.surface !== 'Any surface' ? filters.surface : pickSeeded(PUZZLE_SURFACES, random);
  const archetype = pickSeeded(PUZZLE_ARCHETYPES, random);
  const side = pickSeeded(['forehand', 'backhand', 'body', 'open court'], random);
  const balance = pickSeeded(['balanced', 'slightly late', 'stretched', 'recovering'], random);
  const playerZone = pickSeeded(['behind baseline', 'baseline center', 'inside baseline', 'wide outside doubles alley', 'service line'], random);
  const opponentZone = category === 'Net Play'
    ? pickSeeded(['service line', 'tight to net'], random)
    : pickSeeded(['behind baseline', 'baseline center', 'inside baseline', 'wide forehand corner', 'wide backhand corner'], random);
  const depth = pickSeeded(['deep', 'short', 'mid-court', 'low at feet', 'high shoulder ball'], random);
  const pace = pickSeeded(['heavy', 'fast', 'floating', 'low skidding', 'kicking up'], random);
  const score = pickSeeded(['0–0', '30–30', 'Break point', 'Deuce', '5–5', 'Tiebreak 4–4', 'Set point'], random);
  const handedness = archetype.includes('lefty') ? 'lefty' : pickSeeded(['right-handed', 'left-handed'], random);
  return { seed, category, difficulty, surface, archetype, side, balance, playerZone, opponentZone, depth, pace, score, handedness };
}

function legalPuzzleOptions(scenario) {
  const options = [];
  const add = (label, strength, why, principle) => options.push({ label, strength, why, principle });
  const stretched = scenario.balance === 'stretched' || scenario.playerZone.includes('outside');
  const netOpponent = scenario.category === 'Net Play' || scenario.opponentZone.includes('net') || scenario.opponentZone.includes('service');
  const pressure = /Break|Tiebreak|Set/.test(scenario.score);

  if (scenario.category === 'Serve +1') {
    add('Serve body, then attack the first open ball', 9, 'Body serve reduces the return angle and makes the next shot predictable.', 'Use serve location to earn a playable +1.');
    add('Go for the sideline ace first ball', pressure ? 4 : 6, 'It can work, but the miss cost is high when the score is tight.', 'Risk must match the score.');
    add('Spin serve high to the backhand', scenario.surface === 'Clay court' ? 8 : 7, 'Height and shape can protect the second shot, especially on slower courts.', 'Shape creates time.');
    add('Serve wide and recover slowly', 3, 'The serve opens space, but poor recovery gives it straight back.', 'Serve and recovery are one pattern.');
  } else if (scenario.category === 'Return') {
    add('Block deep through the middle', 8, 'Depth removes the server’s easy first strike and buys recovery time.', 'Neutralize before attacking.');
    add('Step in and pressure the second serve', scenario.depth === 'short' ? 9 : 7, 'This is strong if balance is good and the serve sits up.', 'Attack only when the ball allows it.');
    add('Swing full for a clean sideline winner', pressure ? 3 : 5, 'Low margin if contact is not perfectly timed.', 'Do not let highlights set the target.');
    add('Chip short without disguise', 4, 'The server can move forward and take the point first.', 'Short returns need purpose.');
  } else if (netOpponent) {
    add('Pass low cross-court at the feet', scenario.balance === 'balanced' ? 9 : 7, 'Low and cross-court forces the hardest first volley.', 'Make the net player volley up.');
    add('Lift a high lob over the closed net player', scenario.opponentZone === 'tight to net' ? 9 : 7, 'The lob is preferred when the opponent has overclosed.', 'Use their court position against them.');
    add('Blast flat through the middle', 5, 'It may surprise them, but it gives a comfortable volley height if mistimed.', 'Power is not geometry.');
    add('Drop shot from behind the baseline', 2, 'From deep court it lets the net player move forward, not backward.', 'Do not drop from a losing court position.');
  } else if (scenario.category === 'Defense' || stretched) {
    add('Reset high and deep cross-court', 9, 'Cross-court height gives recovery time and keeps the rally alive.', 'Defense starts with time.');
    add('Slice low through the middle', scenario.surface === 'Grass court' ? 8 : 6, 'A low middle ball can reset the point, especially on faster courts.', 'Change rhythm without opening angles.');
    add('Force a down-the-line winner while late', 3, 'The target is smaller and recovery is worse if you miss timing.', 'Late position needs margin.');
    add('Try a drop shot while stretched', 2, 'The ball usually sits up unless your disguise and touch are perfect.', 'Touch shots need balance.');
  } else if (scenario.category === 'Attack') {
    add('Attack behind the recovering opponent', 9, 'The opponent’s movement creates the opening; you do not need the smallest target.', 'Hit where recovery is weakest.');
    add('Approach deep through the open side', 8, 'Depth makes the pass harder and lets you close the net.', 'Approach behind depth, not hope.');
    add('Flatten to the line at full speed', 5, 'It can finish the point, but the miss rate rises sharply.', 'Finishing shots still need margin.');
    add('Back up and restart neutral', 4, 'Safe, but it gives away the attacking position you earned.', 'Court position is an asset.');
  } else if (scenario.category === 'Pressure') {
    add('Choose a big target and make them play', 9, 'Pressure rewards repeatable targets more than perfect winners.', 'Big-point tennis is target discipline.');
    add('Use your highest percentage pattern', 8, 'A familiar pattern lowers decision noise.', 'Trust the pattern under pressure.');
    add('Change plan during the swing', 2, 'Late decisions create technical errors and bad misses.', 'Commit before contact.');
    add('Aim for highlight sideline immediately', 4, 'The reward is high, but so is the avoidable error risk.', 'Risk must be earned.');
  } else {
    add('Build cross-court height before changing direction', scenario.surface === 'Clay court' ? 9 : 8, 'Height and depth make the next direction change safer.', 'Construct before attacking.');
    add('Take the ball early only if balanced', scenario.balance === 'balanced' ? 8 : 5, 'Early timing is useful when the feet and spacing are set.', 'Timing depends on balance.');
    add('Flatten every ball through the middle', 4, 'It removes shape and gives the opponent rhythm.', 'Surface dictates margin.');
    add('Drop shot from behind the baseline', 3, 'The opponent has too much time unless you are inside court.', 'Court position decides touch.');
  }

  return options
    .sort((a, b) => b.strength - a.strength)
    .slice(0, scenario.difficulty === 'Beginner' ? 3 : 4);
}

function generatePuzzleScenario(seed = state.puzzleSeed, filters = {}) {
  const scenario = tacticalStateFromSeed(seed, filters);
  const options = legalPuzzleOptions(scenario);
  const preferred = options.reduce((best, option, index) => option.strength > options[best].strength ? index : best, 0);
  const best = options[preferred];
  const title = `${scenario.category}: ${scenario.side} decision`;
  const signature = [
    scenario.category, scenario.surface, scenario.difficulty, scenario.archetype,
    scenario.playerZone, scenario.opponentZone, scenario.depth, scenario.balance, best.principle
  ].join('|');
  return {
    id: `scenario-${seed}`,
    seed,
    signature,
    name: title,
    category: scenario.category,
    difficulty: scenario.difficulty,
    surface: scenario.surface,
    opponent: `${scenario.surface} · ${scenario.difficulty} · ${scenario.archetype}`,
    reward: 1,
    tags: [scenario.category, scenario.difficulty, scenario.surface, scenario.archetype],
    scenario,
    steps: [[
      scenario.score,
      `${scenario.handedness} ${scenario.archetype} sends a ${scenario.pace} ${scenario.depth} ball toward your ${scenario.side}.`,
      `You are ${scenario.balance} from ${scenario.playerZone}; opponent is ${scenario.opponentZone}.`,
      options.map(option => option.label),
      preferred,
      `${best.why} Preferred principle: ${best.principle}`
    ]],
    options,
    preferred
  };
}

function nextPuzzleSeed() {
  const recent = readJsonStore('cqPuzzleRecent', []);
  let seed = Math.floor(Date.now() + Math.random() * 100000);
  let scenario = generatePuzzleScenario(seed, {
    category: state.puzzleCategory,
    difficulty: state.puzzleDifficulty,
    surface: state.puzzleSurface
  });
  for (let attempt = 0; attempt < 40 && recent.includes(scenario.signature); attempt += 1) {
    seed += 9973 + attempt;
    scenario = generatePuzzleScenario(seed, {
      category: state.puzzleCategory,
      difficulty: state.puzzleDifficulty,
      surface: state.puzzleSurface
    });
  }
  localStorage.cqPuzzleRecent = JSON.stringify([scenario.signature, ...recent].slice(0, 40));
  return seed;
}

const COMPETE_ROWS = [
  ['Ahmedabad Local Ladder', 'Intermediate', 'Hard court', 'Use as weekly pressure practice'],
  ['Club UTR Night', 'Beginner–advanced', 'Hard court', 'Good for rating-style matches'],
  ['Junior Weekend Draw', 'Age category', 'Mixed courts', 'Best if you need match volume'],
  ['Clay Conditioning Cup', 'Intermediate+', 'Clay', 'Useful for patience and heavier rallies']
];

const TOURNAMENT_SOURCES = [
  ['Local events', 'Club, academy and city tournaments', 'https://www.google.com/search?q=tennis+tournaments+near+me'],
  ['UTR events', 'Open events, junior draws and rating matches', 'https://app.utrsports.net/events'],
  ['ITF calendar', 'World Tennis Tour, juniors, masters and wheelchair events', 'https://www.itftennis.com/en/tournament-calendar/'],
  ['ATP calendar', 'Men’s pro tour events', 'https://www.atptour.com/en/tournaments'],
  ['WTA calendar', 'Women’s pro tour events', 'https://www.wtatennis.com/tournaments'],
  ['USTA search', 'US local, junior and adult events', 'https://playtennis.usta.com/tournaments']
];

const TOURNAMENT_METADATA = [
  {
    id: 'atp-calendar',
    name: 'ATP Tour Calendar',
    tour: 'ATP',
    city: 'Global',
    country: 'International',
    surface: 'Mixed',
    level: 'Professional',
    registration_open_date: null,
    registration_deadline: null,
    registration_url: '',
    official_url: 'https://www.atptour.com/en/tournaments',
    source: 'Official ATP calendar'
  },
  {
    id: 'wta-calendar',
    name: 'WTA Tour Calendar',
    tour: 'WTA',
    city: 'Global',
    country: 'International',
    surface: 'Mixed',
    level: 'Professional',
    registration_open_date: null,
    registration_deadline: null,
    registration_url: '',
    official_url: 'https://www.wtatennis.com/tournaments',
    source: 'Official WTA calendar'
  },
  {
    id: 'itf-world-tennis-tour',
    name: 'ITF World Tennis Tour',
    tour: 'Both',
    city: 'Global',
    country: 'International',
    surface: 'Mixed',
    level: 'Pro / Junior / Masters',
    registration_open_date: null,
    registration_deadline: null,
    registration_url: '',
    official_url: 'https://www.itftennis.com/en/tournament-calendar/',
    source: 'Official ITF calendar'
  },
  {
    id: 'utr-events',
    name: 'UTR Sports Events',
    tour: 'Both',
    city: 'Global',
    country: 'International',
    surface: 'Mixed',
    level: 'Local / Junior / Adult',
    registration_open_date: null,
    registration_deadline: null,
    registration_url: '',
    official_url: 'https://app.utrsports.net/events',
    source: 'UTR event search'
  },
  {
    id: 'usta-tournaments',
    name: 'USTA Tournament Search',
    tour: 'Both',
    city: 'United States',
    country: 'United States',
    surface: 'Mixed',
    level: 'Local / Junior / Adult',
    registration_open_date: null,
    registration_deadline: null,
    registration_url: '',
    official_url: 'https://playtennis.usta.com/tournaments',
    source: 'USTA tournament search'
  }
];

const UPCOMING_PREDICTIONS = Array.isArray(window.COURTIQ_UPCOMING_PREDICTIONS) ? window.COURTIQ_UPCOMING_PREDICTIONS : [];

function groupedUpcomingPredictions(rows = UPCOMING_PREDICTIONS, tour = state.selectedTour) {
  const verified = rows.filter(item => item && item.tournament && item.player_a && item.player_b && item.tour === tour && item.verified_schedule === true);
  const groups = new Map();
  verified.sort((a, b) => String(a.match_at || '').localeCompare(String(b.match_at || ''))).forEach(item => {
    if (!groups.has(item.tournament)) groups.set(item.tournament, []);
    groups.get(item.tournament).push(item);
  });
  return [...groups.entries()];
}

const GEAR_ITEMS = [
  { type: 'Racket', brand: 'Babolat', name: 'Pure Drive', price: '₹19,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Power baseline frame', impact: 'Easy depth and pace; control drops if the swing path gets too flat.', pro: 'Power-first baseline players' },
  { type: 'Racket', brand: 'Babolat', name: 'Pure Drive 98', price: '₹22,999', specs: '98 in² · 305 g · 16×20', level: 'Advanced', style: 'Power/control', impact: 'Sharper targeting than Pure Drive 100, but needs cleaner timing.', pro: 'Aggressive advanced hitters' },
  { type: 'Racket', brand: 'Babolat', name: 'Pure Aero', price: '₹20,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Spin power', impact: 'Helps create shape and net clearance for heavy topspin patterns.', pro: 'Rafael Nadal family style' },
  { type: 'Racket', brand: 'Babolat', name: 'Pure Aero 98', price: '₹23,999', specs: '98 in² · 305 g · 16×20', level: 'Advanced', style: 'Spin/control', impact: 'More precision on fast swings; less free forgiveness than the 100.', pro: 'Carlos Alcaraz family style' },
  { type: 'Racket', brand: 'Babolat', name: 'Pure Strike 100', price: '₹20,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Attack control', impact: 'Rewards taking the ball early and driving through targets.', pro: 'First-strike baseliners' },
  { type: 'Racket', brand: 'Babolat', name: 'Evo Drive', price: '₹13,999', specs: '104 in² · 270 g · 16×17', level: 'Beginner–club', style: 'Comfort power', impact: 'Forgiving sweet spot, easier timing, less plow-through against heavy pace.', pro: 'Best for players building clean contact' },
  { type: 'Racket', brand: 'Babolat', name: 'Evo Aero', price: '₹12,999', specs: '102 in² · 275 g · 16×18', level: 'Beginner–intermediate', style: 'Easy spin', impact: 'Makes topspin easier without demanding a heavy advanced frame.', pro: 'Developing spin players' },
  { type: 'Racket', brand: 'Babolat', name: 'Boost Aero', price: '₹8,999', specs: '102 in² · 260 g · 16×19', level: 'Beginner budget', style: 'Light spin', impact: 'Easy to swing and learn with, but less stable against big hitters.', pro: 'First serious racket' },
  { type: 'Racket', brand: 'Wilson', name: 'Clash 100', price: '₹19,999', specs: '100 in² · 295 g · 16×19', level: 'Intermediate', style: 'Comfort control', impact: 'Soft response for long practice volume with enough modern spin.', pro: 'Arm-friendly all-court players' },
  { type: 'Racket', brand: 'Wilson', name: 'Clash 100L', price: '₹16,999', specs: '100 in² · 280 g · 16×19', level: 'Beginner–intermediate', style: 'Arm-friendly control', impact: 'Comfortable response; good if elbow or shoulder feels stressed.', pro: 'Regular training volume' },
  { type: 'Racket', brand: 'Wilson', name: 'Blade 98', price: '₹22,999', specs: '98 in² · 305 g · 16×19', level: 'Advanced', style: 'Control + feel', impact: 'Rewards early preparation and clean contact; not a free-power frame.', pro: 'Blade-style control frames are common on tour' },
  { type: 'Racket', brand: 'Wilson', name: 'Blade 100L', price: '₹18,999', specs: '100 in² · 285 g · 16×19', level: 'Intermediate', style: 'Lighter feel', impact: 'Blade control feel with easier swing speed and less arm demand.', pro: 'Improving juniors/adults' },
  { type: 'Racket', brand: 'Wilson', name: 'Ultra 100', price: '₹20,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Power', impact: 'Launches the ball with easy pace; pair with spin to control depth.', pro: 'Big-serving baseliners' },
  { type: 'Racket', brand: 'Wilson', name: 'Shift 99', price: '₹21,999', specs: '99 in² · 300 g · 16×20', level: 'Intermediate+', style: 'Modern spin', impact: 'Useful when you want spin and height without losing too much control.', pro: 'Heavy-shape modern hitters' },
  { type: 'Racket', brand: 'Wilson', name: 'Pro Staff 97', price: '₹24,999', specs: '97 in² · 315 g · 16×19', level: 'Advanced', style: 'Precision feel', impact: 'Great feedback and control; demanding if preparation is late.', pro: 'Roger Federer family style' },
  { type: 'Racket', brand: 'Wilson', name: 'RF 01', price: '₹28,999', specs: '98 in² · 300 g · 16×19', level: 'Advanced', style: 'Attacking feel', impact: 'Fast through contact with premium directional control.', pro: 'Roger Federer signature line' },
  { type: 'Racket', brand: 'HEAD', name: 'Speed MP', price: '₹23,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'All-court control', impact: 'Balanced power/control, stable on redirects, reliable for early ball striking.', pro: 'Jannik Sinner family style' },
  { type: 'Racket', brand: 'HEAD', name: 'Speed Pro', price: '₹25,999', specs: '100 in² · 310 g · 18×20', level: 'Advanced', style: 'Control stability', impact: 'More plow-through and lower launch; needs full preparation.', pro: 'Novak Djokovic family style' },
  { type: 'Racket', brand: 'HEAD', name: 'Radical MP', price: '₹22,999', specs: '98 in² · 300 g · 16×19', level: 'Intermediate+', style: 'All-court precision', impact: 'Fast handling and clean direction changes for varied players.', pro: 'Versatile attacking players' },
  { type: 'Racket', brand: 'HEAD', name: 'Gravity MP', price: '₹21,999', specs: '100 in² · 295 g · 16×20', level: 'Intermediate', style: 'Control comfort', impact: 'Large sweet spot feel with controlled launch for long rallies.', pro: 'Baseline patience players' },
  { type: 'Racket', brand: 'HEAD', name: 'Boom MP', price: '₹19,999', specs: '100 in² · 295 g · 16×19', level: 'Intermediate', style: 'Easy power', impact: 'Good pop and comfort when you want depth without forcing.', pro: 'Club attackers' },
  { type: 'Racket', brand: 'HEAD', name: 'Extreme MP', price: '₹21,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Spin power', impact: 'Higher launch and heavier shape for kick serves and topspin rallies.', pro: 'Spin-first baseliners' },
  { type: 'Racket', brand: 'Yonex', name: 'Ezone 100', price: '₹21,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Power + sweet spot', impact: 'Bigger effective hitting area; helps flatter players add margin.', pro: 'Naomi Osaka family style' },
  { type: 'Racket', brand: 'Yonex', name: 'Ezone 98', price: '₹22,999', specs: '98 in² · 305 g · 16×19', level: 'Advanced', style: 'Controlled power', impact: 'Cleaner precision than the 100 with a faster, heavier swing.', pro: 'Attacking advanced baseliners' },
  { type: 'Racket', brand: 'Yonex', name: 'VCORE 100', price: '₹21,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Spin', impact: 'Helps lift the ball high and dip it late into the court.', pro: 'Casper Ruud family style' },
  { type: 'Racket', brand: 'Yonex', name: 'VCORE 98', price: '₹22,999', specs: '98 in² · 305 g · 16×19', level: 'Advanced', style: 'Spin precision', impact: 'Spin-friendly but more demanding; best with confident racket speed.', pro: 'Aggressive spin hitters' },
  { type: 'Racket', brand: 'Yonex', name: 'Percept 100', price: '₹22,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Control feel', impact: 'Comfortable response with accuracy for players who build points.', pro: 'Feel-first baseliners' },
  { type: 'Racket', brand: 'Yonex', name: 'Ezone Ace', price: '₹7,999', specs: '102 in² · 260 g · 16×19', level: 'Beginner budget', style: 'Starter power', impact: 'Easy swing speed for beginners learning timing and contact.', pro: 'Budget first racket' },
  { type: 'Racket', brand: 'Tecnifibre', name: 'TFight 300', price: '₹20,999', specs: '98 in² · 300 g · 16×19', level: 'Advanced', style: 'Speed/control', impact: 'Fast through the ball with crisp response for aggressive timing.', pro: 'Daniil Medvedev family style' },
  { type: 'Racket', brand: 'Tecnifibre', name: 'TFight 305', price: '₹22,999', specs: '98 in² · 305 g · 18×19', level: 'Advanced', style: 'Tour control', impact: 'Lower launch and better directional confidence for clean strikers.', pro: 'Pro-level ball redirectors' },
  { type: 'Racket', brand: 'Tecnifibre', name: 'TF-X1 300', price: '₹18,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Power comfort', impact: 'More free depth and a softer feel than classic control frames.', pro: 'Club power players' },
  { type: 'Racket', brand: 'Dunlop', name: 'CX 200', price: '₹17,999', specs: '98 in² · 305 g · 16×19', level: 'Advanced', style: 'Control value', impact: 'Precise feedback at a lower price than many tour frames.', pro: 'Clean-contact competitors' },
  { type: 'Racket', brand: 'Dunlop', name: 'FX 500', price: '₹16,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Power value', impact: 'Easy pace and depth for players who like first-strike tennis.', pro: 'Budget power frame' },
  { type: 'Racket', brand: 'Dunlop', name: 'SX 300', price: '₹16,999', specs: '100 in² · 300 g · 16×19', level: 'Intermediate+', style: 'Spin value', impact: 'Higher launch and margin for heavy cross-court patterns.', pro: 'Value spin frame' },
  { type: 'Racket', brand: 'Prince', name: 'Warrior 100', price: '₹10,999', specs: '100 in² · 285 g · 16×19', level: 'Budget value', style: 'Easy spin/value', impact: 'Cheap way to get modern specs without a heavy advanced frame.', pro: 'Best cheap pick for improving players' },
  { type: 'Racket', brand: 'Prince', name: 'Phantom 100X 305', price: '₹22,999', specs: '100 in² · 305 g · 16×18', level: 'Advanced', style: 'Flexible control', impact: 'Soft, controlled feel for players who generate their own pace.', pro: 'Classic feel players' },
  { type: 'Racket', brand: 'Prince', name: 'Tour 100P', price: '₹20,999', specs: '100 in² · 305 g · 18×20', level: 'Advanced', style: 'Precise control', impact: 'Predictable launch for point builders who like compact targets.', pro: 'Control/value advanced pick' },
  { type: 'Ball', brand: 'Wilson', name: 'US Open', price: '₹899', specs: 'Hard court · 3 balls', level: 'Match', style: 'Firm + fast', impact: 'Skids through quicker; good for flat hitters and fast-court practice.', pro: 'Hard-court match feel' },
  { type: 'Ball', brand: 'Wilson', name: 'Championship Extra Duty', price: '₹499', specs: 'Hard court · 3 balls', level: 'Budget practice', style: 'Firm value', impact: 'Good for regular hard-court sessions where budget matters.', pro: 'Value hard-court can' },
  { type: 'Ball', brand: 'Wilson', name: 'Triniti', price: '₹699', specs: 'Pressureless-style · 3 balls', level: 'Practice', style: 'Longer life', impact: 'Keeps bounce longer, but feels different from fresh match balls.', pro: 'Ball machine/practice baskets' },
  { type: 'Ball', brand: 'Wilson', name: 'Roland Garros Clay', price: '₹899', specs: 'Clay · 3 balls', level: 'Match', style: 'Clay control', impact: 'Better felt behavior for slower, dirtier clay conditions.', pro: 'Clay-court match prep' },
  { type: 'Ball', brand: 'HEAD', name: 'Tour', price: '₹799', specs: 'Clay/all court · 3 balls', level: 'Practice/match', style: 'Higher bounce', impact: 'Rallies feel heavier; useful for clay and leg conditioning.', pro: 'Good clay conditioning ball' },
  { type: 'Ball', brand: 'HEAD', name: 'Tour XT', price: '₹849', specs: 'Tournament · 3 balls', level: 'Match', style: 'Premium feel', impact: 'Stable bounce for match play and longer hitting sessions.', pro: 'Tournament-style practice' },
  { type: 'Ball', brand: 'HEAD', name: 'Championship', price: '₹449', specs: 'All court · 3 balls', level: 'Budget practice', style: 'Value bounce', impact: 'Good everyday ball when you need quantity for drills.', pro: 'Budget team practice' },
  { type: 'Ball', brand: 'Dunlop', name: 'Australian Open', price: '₹749', specs: 'All court · 3 balls', level: 'Match', style: 'Durable bounce', impact: 'Balanced speed and durability; good for repeated practice sets.', pro: 'Reliable all-court option' },
  { type: 'Ball', brand: 'Dunlop', name: 'ATP Tour', price: '₹799', specs: 'Tournament · 3 balls', level: 'Match', style: 'Premium response', impact: 'Lively feel with reliable bounce for competitive sets.', pro: 'Match-play can' },
  { type: 'Ball', brand: 'Dunlop', name: 'ATP Championship', price: '₹499', specs: 'All court · 3 balls', level: 'Budget match', style: 'Durable value', impact: 'Useful when you want decent match feel without premium pricing.', pro: 'Club match value' },
  { type: 'Ball', brand: 'Dunlop', name: 'Fort All Court', price: '₹699', specs: 'All court · 3 balls', level: 'Practice/match', style: 'Classic durability', impact: 'Heavier, durable feel for long practice blocks.', pro: 'Club staple ball' },
  { type: 'Ball', brand: 'Babolat', name: 'Team All Court', price: '₹599', specs: 'All court · 3 balls', level: 'Practice/match', style: 'Balanced', impact: 'Good middle ground for practice sets on mixed surfaces.', pro: 'All-court club use' },
  { type: 'Ball', brand: 'Babolat', name: 'Gold Championship', price: '₹499', specs: 'All court · 3 balls', level: 'Budget practice', style: 'Value', impact: 'Affordable option for baskets, drills and high-volume hitting.', pro: 'Budget training can' },
  { type: 'Ball', brand: 'Yonex', name: 'Tour', price: '₹799', specs: 'Tournament · 4 balls', level: 'Match', style: 'Consistent bounce', impact: 'Good for players who like a controlled, predictable response.', pro: 'Tournament practice' },
  { type: 'String', brand: 'Babolat', name: 'RPM Blast', price: '₹2,499', specs: 'Poly · spin/control', level: 'Advanced', style: 'Spin grip', impact: 'Adds bite and control; can feel harsh if tension is too high.', pro: 'Heavy topspin players' },
  { type: 'String', brand: 'Babolat', name: 'RPM Rough', price: '₹2,499', specs: 'Textured poly · spin', level: 'Advanced', style: 'Extra bite', impact: 'More grab on the ball; durability and comfort depend on tension.', pro: 'Spin-focused hitters' },
  { type: 'String', brand: 'Babolat', name: 'RPM Soft', price: '₹1,899', specs: 'Softer mono · control', level: 'Intermediate', style: 'Comfort control', impact: 'More forgiving than stiff polys while keeping control feel.', pro: 'Poly transition players' },
  { type: 'String', brand: 'Babolat', name: 'Xcel', price: '₹2,199', specs: 'Multifilament · comfort', level: 'All levels', style: 'Arm comfort', impact: 'Soft depth and comfort; less spin bite than polyester.', pro: 'Arm-friendly setup' },
  { type: 'String', brand: 'Babolat', name: 'Touch VS', price: '₹5,999', specs: 'Natural gut · power/feel', level: 'Premium', style: 'Feel + power', impact: 'Elite comfort and power, but expensive and weather-sensitive.', pro: 'Premium hybrid setups' },
  { type: 'String', brand: 'Wilson', name: 'NXT', price: '₹2,199', specs: 'Multifilament · comfort', level: 'All levels', style: 'Comfort + depth', impact: 'More power and comfort; breaks faster than polyester.', pro: 'Good for arm protection' },
  { type: 'String', brand: 'Wilson', name: 'Sensation', price: '₹999', specs: 'Multifilament · value', level: 'Beginner–club', style: 'Comfort value', impact: 'Soft feel at a lower price; not for heavy string breakers.', pro: 'Budget comfort setup' },
  { type: 'String', brand: 'Wilson', name: 'Revolve', price: '₹1,499', specs: 'Poly · spin', level: 'Intermediate+', style: 'Spin/control', impact: 'Helps snapback and spin, but keep tension sensible for comfort.', pro: 'Spin learners moving to poly' },
  { type: 'String', brand: 'Luxilon', name: 'ALU Power', price: '₹2,699', specs: 'Poly · tour control', level: 'Advanced', style: 'Crisp control', impact: 'Premium control and response; best for strong, fast swings.', pro: 'Tour-level hybrid/main string' },
  { type: 'String', brand: 'Luxilon', name: '4G', price: '₹2,499', specs: 'Poly · tension hold', level: 'Advanced', style: 'Stable control', impact: 'Better tension maintenance, firmer response, strong directional control.', pro: 'Control-focused competitors' },
  { type: 'String', brand: 'Luxilon', name: 'Element', price: '₹2,299', specs: 'Softer poly · feel', level: 'Intermediate+', style: 'Feel control', impact: 'More comfort than many polys with useful control.', pro: 'Comfort-minded poly users' },
  { type: 'String', brand: 'HEAD', name: 'Lynx Tour', price: '₹1,699', specs: 'Shaped poly · control', level: 'Intermediate+', style: 'Spin/control', impact: 'Predictable response for players who swing fast through the ball.', pro: 'Modern topspin baseliners' },
  { type: 'String', brand: 'HEAD', name: 'Velocity MLT', price: '₹1,099', specs: 'Multifilament · comfort', level: 'All levels', style: 'Comfort value', impact: 'Soft response and easy depth for club players.', pro: 'Arm-friendly value' },
  { type: 'String', brand: 'Solinco', name: 'Hyper-G', price: '₹1,299', specs: 'Shaped poly · spin', level: 'Intermediate+', style: 'Spin bite', impact: 'Grabs the ball well and rewards vertical racket speed.', pro: 'Heavy spin players' },
  { type: 'String', brand: 'Solinco', name: 'Tour Bite', price: '₹1,399', specs: 'Shaped poly · control', level: 'Advanced', style: 'Sharp control', impact: 'Firm, controlled response for big cuts at the ball.', pro: 'Aggressive baseliners' },
  { type: 'String', brand: 'Yonex', name: 'PolyTour Pro', price: '₹1,499', specs: 'Poly · control', level: 'Intermediate+', style: 'Smooth control', impact: 'Controlled, reliable response without extreme harshness.', pro: 'All-court competitors' },
  { type: 'Shoes', brand: 'ASICS', name: 'Gel Resolution', price: '₹12,999', specs: 'Hard/clay models', level: 'Competitive', style: 'Lateral stability', impact: 'Better braking and support for aggressive movers.', pro: 'Best for hard training days' },
  { type: 'Shoes', brand: 'ASICS', name: 'Court FF', price: '₹14,999', specs: 'Premium stability', level: 'Competitive+', style: 'Explosive support', impact: 'Stable for hard stops, slides and repeated direction changes.', pro: 'Novak Djokovic family line' },
  { type: 'Shoes', brand: 'ASICS', name: 'Solution Speed FF', price: '₹11,999', specs: 'Lightweight speed', level: 'Competitive', style: 'Fast movement', impact: 'Quick first step with less heavy-duty support than Resolution.', pro: 'Fast all-court movers' },
  { type: 'Shoes', brand: 'Nike', name: 'Vapor Pro', price: '₹11,999', specs: 'Lightweight match shoe', level: 'Competitive', style: 'Speed', impact: 'Fast first step and low court feel; less tank-like support.', pro: 'Speed-first players' },
  { type: 'Shoes', brand: 'Nike', name: 'Vapor Lite', price: '₹7,999', specs: 'Lightweight value', level: 'Beginner–club', style: 'Speed value', impact: 'Easy entry into tennis shoes without premium pricing.', pro: 'Budget speed shoe' },
  { type: 'Shoes', brand: 'Nike', name: 'GP Challenge', price: '₹12,999', specs: 'Support/speed', level: 'Competitive', style: 'Balanced', impact: 'More support than pure speed shoes for players who slide and brake hard.', pro: 'Aggressive movers' },
  { type: 'Shoes', brand: 'Adidas', name: 'Barricade', price: '₹10,999', specs: 'Durability/stability', level: 'Competitive', style: 'Support', impact: 'Strong for heavy movers who burn through shoes.', pro: 'Long practice blocks' },
  { type: 'Shoes', brand: 'Adidas', name: 'Adizero Ubersonic', price: '₹11,999', specs: 'Speed shoe', level: 'Competitive', style: 'Light movement', impact: 'Fast, low feel for quick players; less armored than Barricade.', pro: 'Speed-first baseline movers' },
  { type: 'Shoes', brand: 'Adidas', name: 'Solematch Control', price: '₹8,999', specs: 'Support value', level: 'Club', style: 'Stable value', impact: 'Good support for regular club tennis without premium price.', pro: 'Value support shoe' },
  { type: 'Shoes', brand: 'New Balance', name: 'Fresh Foam X 996', price: '₹10,999', specs: 'Lightweight speed', level: 'Competitive', style: 'Cushioned speed', impact: 'Good underfoot comfort while staying quick around the baseline.', pro: 'Fast practice/match shoe' },
  { type: 'Shoes', brand: 'New Balance', name: 'Coco CG2', price: '₹13,999', specs: 'Signature support', level: 'Competitive+', style: 'Explosive support', impact: 'Built for powerful cuts and quick recovery steps.', pro: 'Coco Gauff signature line' },
  { type: 'Shoes', brand: 'K-Swiss', name: 'Hypercourt Express', price: '₹8,999', specs: 'Comfort value', level: 'Club', style: 'Comfortable support', impact: 'Easy break-in and comfortable for regular practice.', pro: 'Club comfort staple' },
  { type: 'Shoes', brand: 'K-Swiss', name: 'Ultrashot', price: '₹10,999', specs: 'Stability/durability', level: 'Competitive', style: 'Support', impact: 'Better for hard movers who need outsole life and side support.', pro: 'Durability-focused players' },
  { type: 'Shoes', brand: 'Babolat', name: 'Jet Mach', price: '₹11,999', specs: 'Speed shoe', level: 'Competitive', style: 'Fast response', impact: 'Light and explosive for players who attack short balls quickly.', pro: 'Speed attackers' },
  { type: 'Shoes', brand: 'Babolat', name: 'Propulse Fury', price: '₹10,999', specs: 'Support shoe', level: 'Competitive', style: 'Stability', impact: 'More support and durability for hard training blocks.', pro: 'Heavy movers' },
  { type: 'Shoes', brand: 'On', name: 'THE ROGER Pro', price: '₹15,999', specs: 'Premium match shoe', level: 'Competitive+', style: 'Responsive support', impact: 'Premium court feel with controlled support for aggressive movement.', pro: 'Iga Swiatek / Ben Shelton family line' }
];

const FEATURED_GEAR_ITEMS = [...GEAR_ITEMS];

function addLargeGearCatalog() {
  const seen = new Set(GEAR_ITEMS.map(item => `${item.type}|${item.brand}|${item.name}`));
  const add = item => {
    const key = `${item.type}|${item.brand}|${item.name}`;
    if (!seen.has(key)) {
      seen.add(key);
      GEAR_ITEMS.push(item);
    }
  };

  const racketFamilies = [
    ['Wilson', ['Blade', 'Clash', 'Ultra', 'Shift', 'Pro Staff', 'RF', 'Burn', 'Triad']],
    ['Babolat', ['Pure Drive', 'Pure Aero', 'Pure Strike', 'Evo Drive', 'Evo Aero', 'Boost Drive', 'Boost Aero']],
    ['HEAD', ['Speed', 'Radical', 'Gravity', 'Boom', 'Extreme', 'Prestige', 'Instinct', 'Challenge']],
    ['Yonex', ['Ezone', 'VCORE', 'Percept', 'Astrel', 'Ezone Ace']],
    ['Tecnifibre', ['TFight', 'TF-X1', 'Tempo', 'T-Rebound']],
    ['Dunlop', ['CX', 'FX', 'SX', 'LX', 'Nitro']],
    ['Prince', ['Phantom', 'Tour', 'Warrior', 'Ripstick', 'Beast', 'Textreme']],
    ['Volkl', ['V-Cell', 'Vostra', 'Organix', 'Power Bridge']],
    ['ProKennex', ['Ki', 'Q+', 'Black Ace', 'Kinetic']],
    ['Artengo', ['TR', 'TR Pro', 'TR Lite']],
    ['Diadem', ['Nova', 'Elevate', 'Axis']],
    ['Lacoste', ['L20', 'L23', 'LT']],
    ['Gamma', ['RZR', 'Quick Kids', 'Obsidian']]
  ];
  const racketVariants = ['100', '100L', '100UL', '98', '98L', '97', 'Pro', 'MP', 'Team', 'Tour', 'Lite', 'Plus', 'Junior 26', 'Junior 25'];
  const racketSpecs = [
    ['100 in² · 300 g · 16×19', 'Intermediate+', 'All-court', 'Balanced response for rally depth, spin and controlled power.'],
    ['100 in² · 285 g · 16×19', 'Beginner–intermediate', 'Easy swing', 'Lighter swing weight helps developing players accelerate cleanly.'],
    ['98 in² · 305 g · 16×19', 'Advanced', 'Control', 'Smaller head rewards precise contact and confident preparation.'],
    ['102 in² · 270 g · 16×19', 'Beginner–club', 'Forgiving', 'Larger face and low weight make timing easier under pressure.'],
    ['100 in² · 310 g · 18×20', 'Advanced', 'Stability', 'Heavier control frame for clean strikers who create their own pace.']
  ];

  racketFamilies.forEach(([brand, families]) => {
    families.forEach(family => {
      racketVariants.forEach((variant, index) => {
        const [specs, level, style, impact] = racketSpecs[index % racketSpecs.length];
        add({
          type: 'Racket',
          brand,
          name: `${family} ${variant}`,
          price: index % 5 === 0 ? '₹8,999–₹13,999' : index % 3 === 0 ? '₹14,999–₹19,999' : '₹20,999–₹29,999',
          specs,
          level,
          style,
          impact,
          pro: `${brand} ${family} official-family option`
        });
      });
    });
  });

  const ballFamilies = [
    ['Wilson', ['US Open', 'Roland Garros', 'Triniti', 'Championship', 'Team Practice', 'Starter Play']],
    ['HEAD', ['Tour', 'Tour XT', 'Pro', 'Championship', 'Team', 'Tip Green']],
    ['Dunlop', ['Australian Open', 'ATP Tour', 'ATP Championship', 'Fort All Court', 'Grand Prix', 'Stage 1 Green']],
    ['Babolat', ['Team All Court', 'Gold Championship', 'French Open', 'Team Clay', 'Red Foam', 'Orange']],
    ['Yonex', ['Tour', 'Championship', 'Muscle Power', 'Training']],
    ['Prince', ['Tour', 'Championship', 'NX Tour', 'Practice']],
    ['Tecnifibre', ['X-One', 'Court', 'Club', 'Stage 1']]
  ];
  const ballPacks = ['3-ball can', '4-ball can', 'case 24 cans', 'practice bucket', 'clay duty', 'extra duty', 'regular duty'];
  ballFamilies.forEach(([brand, families]) => {
    families.forEach(family => {
      ballPacks.forEach((pack, index) => add({
        type: 'Ball',
        brand,
        name: `${family} ${pack}`,
        price: index < 2 ? '₹399–₹999' : index === 2 ? '₹8,999–₹14,999' : '₹999–₹4,999',
        specs: pack.includes('case') ? 'Case · match/practice' : pack.includes('bucket') ? 'Practice bucket' : pack,
        level: pack.includes('Stage') || family.includes('Starter') ? 'Beginner/junior' : pack.includes('Tour') || family.includes('Open') ? 'Match' : 'Practice',
        style: pack.includes('clay') ? 'Clay feel' : pack.includes('extra') ? 'Hard-court durability' : 'All-court',
        impact: pack.includes('clay') ? 'Controls fluff and bounce better on clay.' : pack.includes('extra') ? 'Handles abrasive hard courts longer.' : 'Useful for matching practice ball feel to your surface.',
        pro: `${brand} official ball-family option`
      }));
    });
  });

  const stringFamilies = [
    ['Babolat', ['RPM Blast', 'RPM Rough', 'RPM Soft', 'Xcel', 'Touch VS', 'Addiction', 'Synthetic Gut']],
    ['Wilson', ['NXT', 'Sensation', 'Revolve', 'Natural Gut', 'Synthetic Gut Power', 'Duo Control']],
    ['Luxilon', ['ALU Power', '4G', 'Element', 'Savage', 'Original', 'Eco Power']],
    ['HEAD', ['Lynx Tour', 'Lynx', 'Velocity MLT', 'Hawk', 'Reflex MLT', 'Synthetic Gut PPS']],
    ['Solinco', ['Hyper-G', 'Tour Bite', 'Confidential', 'Outlast', 'Vanquish', 'Revolution']],
    ['Yonex', ['PolyTour Pro', 'PolyTour Strike', 'PolyTour Rev', 'Rexis Speed', 'Rexis Comfort']],
    ['Tecnifibre', ['X-One Biphase', 'Razor Code', 'Ice Code', 'Triax', 'NRG2', 'Multifeel']],
    ['Dunlop', ['Explosive Spin', 'Explosive Bite', 'Iconic All', 'Silk Pro']],
    ['Gamma', ['Moto', 'Live Wire', 'TNT2', 'Ocho']]
  ];
  const gauges = ['16', '16L', '17', '18'];
  const tensions = ['low tension', 'mid tension', 'high control', 'hybrid cross'];
  stringFamilies.forEach(([brand, families]) => {
    families.forEach(family => {
      gauges.forEach(gauge => {
        tensions.forEach((setup, index) => add({
          type: 'String',
          brand,
          name: `${family} ${gauge} ${setup}`,
          price: family.includes('Gut') || family.includes('VS') ? '₹4,999–₹7,999' : index === 3 ? '₹1,999–₹3,499' : '₹899–₹2,499',
          specs: `${gauge} gauge · ${setup}`,
          level: family.includes('Gut') || family.includes('X-One') ? 'Premium' : family.includes('Blast') || family.includes('ALU') || family.includes('Hyper') ? 'Advanced' : 'All levels',
          style: family.includes('NXT') || family.includes('Xcel') || family.includes('Velocity') ? 'Comfort' : family.includes('RPM') || family.includes('Hyper') || family.includes('Lynx') ? 'Spin/control' : 'Balanced',
          impact: setup.includes('low') ? 'Adds easier depth and comfort.' : setup.includes('high') ? 'Adds control but can feel firmer.' : setup.includes('hybrid') ? 'Balances comfort, power and control.' : 'Reliable all-around string response.',
          pro: `${brand} official string-family option`
        }));
      });
    });
  });

  const shoeFamilies = [
    ['ASICS', ['Gel Resolution', 'Court FF', 'Solution Speed FF', 'Game FF', 'Dedicate']],
    ['Nike', ['Vapor Pro', 'Vapor Lite', 'GP Challenge', 'Zoom NXT', 'Court Lite']],
    ['Adidas', ['Barricade', 'Adizero Ubersonic', 'Solematch Control', 'CourtJam Control', 'Defiant Speed']],
    ['New Balance', ['Fresh Foam X 996', 'Coco CG2', 'FuelCell 996', 'Lav', '806']],
    ['K-Swiss', ['Hypercourt Express', 'Ultrashot', 'SpeedTrac', 'Express Light', 'Bigshot Light']],
    ['Babolat', ['Jet Mach', 'Propulse Fury', 'SFX', 'Pulsion']],
    ['On', ['THE ROGER Pro', 'THE ROGER Clubhouse Pro', 'THE ROGER Advantage']],
    ['Wilson', ['Rush Pro', 'Kaos Swift', 'Hurakn Pro', 'RKA']],
    ['Yonex', ['Power Cushion Eclipsion', 'Sonicage', 'Fusionrev', 'Lumio']]
  ];
  const shoeCuts = ['men hard court', 'women hard court', 'clay outsole', 'all court', 'wide fit', 'junior'];
  shoeFamilies.forEach(([brand, families]) => {
    families.forEach(family => {
      shoeCuts.forEach((cut, index) => add({
        type: 'Shoes',
        brand,
        name: `${family} ${cut}`,
        price: index === 5 ? '₹4,999–₹7,999' : index === 4 ? '₹8,999–₹12,999' : '₹7,999–₹15,999',
        specs: cut,
        level: index === 5 ? 'Junior' : family.includes('Resolution') || family.includes('Barricade') || family.includes('Court FF') ? 'Competitive+' : 'Club–competitive',
        style: cut.includes('clay') ? 'Clay traction' : cut.includes('wide') ? 'Comfort fit' : family.includes('Speed') || family.includes('Vapor') || family.includes('Ubersonic') ? 'Speed' : 'Support',
        impact: cut.includes('clay') ? 'Better grip and controlled sliding on clay.' : cut.includes('wide') ? 'More room for wider feet during long sessions.' : 'Court-specific support for braking, recovery and direction changes.',
        pro: `${brand} official shoe-family option`
      }));
    });
  });
}

// Keep the shopper-facing catalog to explicitly listed products only.
// addLargeGearCatalog intentionally not called: it creates synthetic variants
// that should never be shown as real inventory.
const GEAR_INDEX = window.COURTIQ_GEAR_INDEX || { metadata: {}, products: [] };
const BOOTSTRAP_GEAR_ITEMS = GEAR_ITEMS.map(normalizeLegacyGearItem);
const REAL_GEAR_ITEMS = (Array.isArray(GEAR_INDEX.products) && GEAR_INDEX.products.length
  ? GEAR_INDEX.products.map(normalizeIndexedGearItem)
  : BOOTSTRAP_GEAR_ITEMS);
const FEATURED_REAL_GEAR_ITEMS = REAL_GEAR_ITEMS.slice(0, 12);

const SECURITY_ITEMS = [
  'Device-local profile by default',
  'Opponent-consent check before match video analysis',
  'Video uploads are temporary and cleaned after analyzer processing',
  'Generated photo files are user-controlled',
  'Chat requests require acceptance before conversation',
  'Unsafe sharing warnings for contact, address and location'
];

function savedRouteForProduct(product) {
  const key = product === 'predict' ? 'cqLastPredictRoute' : 'cqLastTrainRoute';
  const route = normalizeRoute(localStorage.getItem(key));
  return route.product === product ? route : defaultRouteForProduct(product);
}

const state = {
  route: normalizeRoute(location.hash.slice(1) || 'entry').id,
  page: normalizeRoute(location.hash.slice(1) || 'entry').page,
  product: localStorage.cqProduct || 'train',
  selectedTour: (localStorage.cqTour || 'ATP').toUpperCase() === 'WTA' ? 'WTA' : 'ATP',
  player1: localStorage.cqP1 || 'Carlos Alcaraz',
  player2: localStorage.cqP2 || 'Jannik Sinner',
  draftP1: localStorage.cqP1 || 'Carlos Alcaraz',
  draftP2: localStorage.cqP2 || 'Jannik Sinner',
  activeSlot: 'player1',
  search: '',
  slam: localStorage.cqSlam || 'Hard Court',
  selectedVideo: null,
  puzzleId: Number(localStorage.cqPuzzleId || 0),
  puzzleSeed: Number(localStorage.cqPuzzleSeed || Date.now()),
  puzzleStep: Number(localStorage.cqPuzzleStep || 0),
  puzzleCategory: localStorage.cqPuzzleCategory || 'Random',
  puzzleDifficulty: localStorage.cqPuzzleDifficulty || 'Any difficulty',
  puzzleSurface: localStorage.cqPuzzleSurface || 'Any surface',
  puzzleStats: readJsonStore('cqPuzzleStats', { attempted: 0, correct: 0, categories: {} }),
  puzzleFeedback: '',
  puzzleLastChoice: '',
  puzzleLastCorrect: null,
  backendPrediction: null,
  predictionLoading: false,
  predictionError: '',
  learnLevel: ['Beginner', 'Intermediate', 'Advanced'].includes(localStorage.cqLearnLevel) ? localStorage.cqLearnLevel : 'Beginner',
  learnCategory: '',
  learnOpenLesson: '',
  learnLesson: 'contact',
  learnChoice: { contact: 'ideal', net: 'pass', recovery: 'turn' },
  learnStep: 1
};

const TRAIN_STORE_KEY = 'cqTrainPerformance';
const VIDEO_LIMIT_BYTES = 80 * 1024 * 1024;
const VIDEO_EXTENSIONS = ['mp4', 'mov', 'm4v', 'webm'];
const VIDEO_MIME_TYPES = ['video/mp4', 'video/quicktime', 'video/webm', 'video/x-m4v'];

function trainStore() {
  const fallback = { analyses: [], plan: [], sessions: [], activeSession: null, activePlan: null };
  const saved = readJsonStore(TRAIN_STORE_KEY, fallback);
  return {
    analyses: Array.isArray(saved.analyses) ? saved.analyses : [],
    plan: Array.isArray(saved.plan) ? saved.plan : [],
    sessions: Array.isArray(saved.sessions) ? saved.sessions : [],
    activeSession: saved.activeSession || null,
    activePlan: saved.activePlan || null
  };
}

function saveTrainStore(store) {
  localStorage.setItem(TRAIN_STORE_KEY, JSON.stringify(store));
}

function latestAnalysis() {
  return trainStore().analyses[0] || null;
}

function qualityLabel(confidence) {
  const value = Number(confidence || 0);
  if (value >= 0.72) return 'High visibility';
  if (value >= 0.48) return 'Usable visibility';
  if (value > 0) return 'Low visibility';
  return 'Not measured';
}

function metricLabel(name) {
  return String(name || '')
    .replaceAll('_', ' ')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function metricBucket(name) {
  const key = String(name || '');
  if (key.includes('knee') || key.includes('hip')) return 'Lower body';
  if (key.includes('elbow') || key.includes('shoulder')) return 'Upper body';
  if (key.includes('tilt')) return 'Posture';
  return 'Movement';
}

function detectionValue(value) {
  if (value === true) return 'Detected';
  if (value === false) return 'Not confirmed';
  if (value == null || value === '') return 'Unknown';
  return String(value);
}

function videoDetectionCardsMarkup(detection = {}) {
  const items = [
    ['Player', detectionValue(detection.player_visible)],
    ['Body view', detectionValue(detection.body_visibility)],
    ['Camera', detectionValue(detection.view_orientation)],
    ['Serve sequence', detectionValue(detection.serve_sequences_present)],
    ['Groundstrokes', detectionValue(detection.groundstroke_sequences_present)],
    ['Movement', detectionValue(detection.movement_analysis_reliable)],
    ['Rally context', detectionValue(detection.rally_context_identified)]
  ];
  return `<section class="detected-actions">
    <div><span class="eyebrow">DETECTED</span><h3>What this video supports</h3></div>
    <div class="detected-grid">
      ${items.map(([label, value]) => `<article>
        <span>${escapeHtml(label)}</span>
        <b>${escapeHtml(value)}</b>
      </article>`).join('')}
    </div>
  </section>`;
}

function videoLimitationsMarkup(detection = {}) {
  const limitations = Array.isArray(detection.limitations) ? detection.limitations : [];
  if (!limitations.length) return '';
  return `<details class="analysis-limitations">
    <summary>Analysis limitations</summary>
    <p>Pose-based only · Ball and racket tracking are not measured.</p>
  </details>`;
}

function recommendationFromMetric(name, metric) {
  const key = String(name || '');
  const mean = Number(metric?.mean || 0);
  if (key.includes('knee')) {
    return {
      title: 'Build a stable athletic base',
      saw: `${metricLabel(name)} averaged ${Number.isFinite(mean) ? Math.round(mean) : '—'}° in visible frames.`,
      why: 'A stable knee-over-foot base helps you load without collapsing or standing upright too early.',
      drill: '3 × 6 lateral bound-and-stick reps each side, then 2 × 8 shadow swings holding the loaded base for one second.',
      target: 'Quiet landing with knee tracking over toes.'
    };
  }
  if (key.includes('elbow')) {
    return {
      title: 'Create cleaner contact spacing',
      saw: `${metricLabel(name)} produced enough visible frames for a contact-spacing check.`,
      why: 'Crowded elbows usually mean the ball is too close; stretched elbows usually mean late footwork.',
      drill: 'Place a cone one racket-length from your hip. Hit 3 × 8 controlled balls while keeping contact in that spacing window.',
      target: 'Contact feels in front, not jammed beside the body.'
    };
  }
  if (key.includes('shoulder')) {
    return {
      title: 'Turn before the ball arrives',
      saw: `${metricLabel(name)} showed visible shoulder-line change through the clip.`,
      why: 'Earlier shoulder preparation gives power from the body instead of forcing the arm to rescue the shot.',
      drill: 'Shadow five slow unit turns, then hit 3 × 8 cross-court balls with shoulders prepared before the bounce.',
      target: 'Preparation finished before the bounce.'
    };
  }
  if (key.includes('hip')) {
    return {
      title: 'Link hips to recovery',
      saw: `${metricLabel(name)} was visible enough to review body alignment.`,
      why: 'Hip control affects how quickly you recover after contact and whether the next ball feels rushed.',
      drill: 'Hit one ball, recover behind a centre marker, split-step, then repeat for 3 × 45 seconds.',
      target: 'First recovery step starts immediately after finish.'
    };
  }
  return {
    title: 'Improve the clearest visible metric',
    saw: `${metricLabel(name)} was measured from the clip.`,
    why: 'The most reliable visible signal should drive the next practice block.',
    drill: 'Repeat 3 short sets where you focus on one cue only, then upload a second clip from the same angle.',
    target: 'Cleaner repeatability from clip to clip.'
  };
}

function recommendationsFromMetrics(metrics) {
  const entries = Object.entries(metrics || {});
  if (!entries.length) return [];
  return entries
    .sort((a, b) => Number(b[1]?.confidence || 0) - Number(a[1]?.confidence || 0))
    .slice(0, 4)
    .map(([name, metric]) => recommendationFromMetric(name, metric));
}

function persistAnalysisRecord(file, payload) {
  const analysis = payload.analysis || {};
  if (analysis.status !== 'ok') return null;
  const store = trainStore();
  const metrics = analysis.metrics || {};
  const recommendations = recommendationsFromMetrics(metrics);
  const record = {
    id: `analysis-${Date.now()}`,
    createdAt: new Date().toISOString(),
    focus: 'Automatic detection',
    filename: file.name,
    sizeMb: Number((file.size / 1024 / 1024).toFixed(1)),
    frames: Number(analysis.frames_processed || 0),
    durationMs: Number(payload.duration_ms || 0),
    metrics,
    recommendations
  };
  store.analyses = [record, ...store.analyses].slice(0, 12);
  saveTrainStore(store);
  return record;
}

function addAnalysisToPlan(record = latestAnalysis()) {
  if (!record?.recommendations?.length) return false;
  const store = trainStore();
  const existing = new Set(store.plan.map(item => item.title));
  const additions = record.recommendations
    .filter(item => !existing.has(item.title))
    .map((item, index) => ({
      id: `plan-${Date.now()}-${index}`,
      title: item.title,
      drill: item.drill,
      target: item.target,
      source: record.focus,
      done: false
    }));
  store.plan = [...additions, ...store.plan].slice(0, 10);
  saveTrainStore(store);
  return additions.length > 0;
}

const TRAINING_GOALS = ['Serve', 'Return', 'Forehand', 'Backhand', 'Volleys', 'Footwork', 'Movement', 'Consistency', 'Rally tolerance', 'Defense', 'Attack', 'Transition game', 'Net play', 'Serve +1', 'Return +1', 'Match fitness', 'Pressure points', 'Tiebreak preparation', 'Clay-court movement', 'Hard-court patterns', 'Grass-court patterns', 'General match preparation'];
const PLAN_LENGTHS = [0, 1, 2, 4, 6, 8];
const PLAN_LEVELS = ['Beginner', 'Intermediate', 'Advanced', 'Competitive'];
const DRILL_LIBRARY = [
  { name: 'Service-box rhythm', category: 'Serve', objective: 'Repeat a balanced toss and relaxed acceleration', setup: 'Six balls; serve from halfway between service line and baseline', execution: 'Hit three serves to each box at 60%, hold the finish, then repeat from baseline', difficulty: 1, equipment: ['court', 'balls'], mode: 'solo', tags: ['Serve', 'Consistency'] },
  { name: 'Serve +1 lanes', category: 'Serve +1', objective: 'Connect serve placement to the first groundstroke', setup: 'Mark wide, body and T targets plus two deep first-ball lanes', execution: 'Serve to one called target, recover, then drive the fed ball through the opposite lane', difficulty: 3, equipment: ['court', 'balls', 'cones'], mode: 'partner', tags: ['Serve', 'Serve +1', 'Attack'] },
  { name: 'Split-read return', category: 'Return', objective: 'Time the split step and neutralize direction', setup: 'Partner serves at 60–80%; mark a deep middle target', execution: 'Split as the server contacts, shorten the backswing and land eight returns beyond the service line', difficulty: 2, equipment: ['court', 'balls'], mode: 'partner', tags: ['Return', 'Return +1', 'Defense'] },
  { name: 'Crosscourt height ladder', category: 'Groundstroke', objective: 'Build repeatable net clearance and depth', setup: 'Mark a deep crosscourt target and three net-height windows', execution: 'Hit sets of six at safe, neutral and attacking height without changing direction', difficulty: 2, equipment: ['court', 'balls', 'cones'], mode: 'partner', tags: ['Forehand', 'Backhand', 'Consistency', 'Rally tolerance'] },
  { name: 'Recovery triangle', category: 'Movement', objective: 'Recover immediately after contact', setup: 'Place cones at centre mark and two wide contact points', execution: 'Move wide, shadow or hit, crossover toward centre, split, then move to the other side', difficulty: 2, equipment: ['cones'], mode: 'solo', tags: ['Footwork', 'Movement', 'Defense', 'Clay-court movement'] },
  { name: 'Short-ball transition', category: 'Attack', objective: 'Recognize and close on a short ball', setup: 'Feeder alternates neutral and short balls; mark approach target', execution: 'Hold neutral depth until the short ball, approach behind the shot and finish with one volley', difficulty: 3, equipment: ['court', 'balls', 'cones'], mode: 'partner', tags: ['Attack', 'Transition game', 'Net play', 'Volleys'] },
  { name: 'Two-volley close', category: 'Volleys', objective: 'Control first volley depth and close efficiently', setup: 'Start at service line with feeder at baseline', execution: 'First volley beyond service line, move forward, second volley to open court; six repetitions each side', difficulty: 2, equipment: ['court', 'balls'], mode: 'partner', tags: ['Volleys', 'Net play', 'Transition game'] },
  { name: 'Defense-to-neutral', category: 'Defense', objective: 'Reset a stretched rally without overplaying', setup: 'Feeder sends one wide ball followed by a neutral ball', execution: 'Lift the defensive ball deep middle, recover, then play the next ball crosscourt', difficulty: 3, equipment: ['court', 'balls'], mode: 'partner', tags: ['Defense', 'Movement', 'Rally tolerance'] },
  { name: 'Twenty-ball tolerance', category: 'Consistency', objective: 'Maintain shape and spacing under repetition', setup: 'Crosscourt cooperative rally', execution: 'Reach 20 balls before changing direction; restart immediately after an error', difficulty: 2, equipment: ['court', 'balls'], mode: 'partner', tags: ['Consistency', 'Rally tolerance', 'Match fitness'] },
  { name: 'Scoreboard pressure set', category: 'Pressure', objective: 'Execute high-percentage patterns under score pressure', setup: 'Play points beginning at 30–30 or 5–5', execution: 'Call the first two-shot pattern before every point and review only whether it was executed', difficulty: 4, equipment: ['court', 'balls'], mode: 'partner', tags: ['Pressure points', 'Tiebreak preparation', 'General match preparation'] },
  { name: 'Surface pattern rehearsal', category: 'Tactics', objective: 'Match trajectory and positioning to the surface', setup: 'Choose clay, hard or grass pattern before the block', execution: 'Run eight points using height and patience on clay, balanced first-strike on hard, or low compact patterns on grass', difficulty: 3, equipment: ['court', 'balls'], mode: 'partner', tags: ['Clay-court movement', 'Hard-court patterns', 'Grass-court patterns', 'General match preparation'] },
  { name: 'Movement interval six', category: 'Fitness', objective: 'Repeat tennis movement without losing posture', setup: 'Three cones across baseline; racket in hand', execution: 'Six 30-second work bouts with 30 seconds recovery; split at centre every repetition', difficulty: 3, equipment: ['cones', 'racket'], mode: 'solo', tags: ['Match fitness', 'Footwork', 'Movement'] }
];

function planPhase(week, weeks) {
  if (weeks <= 1) return 'Technique and repeatability';
  const ratio = week / weeks;
  if (ratio <= 0.25) return 'Technique and repeatability';
  if (ratio <= 0.5) return 'Movement integration';
  if (ratio <= 0.75) return 'Pattern execution';
  return 'Pressure and match transfer';
}

function drillDose(drill, minutes, phase, level) {
  const reps = Math.max(2, Math.round(minutes / 5));
  return `${minutes} min · ${reps} focused sets · ${phase}${level === 'Beginner' ? ' at controlled pace' : ''}`;
}

function generateTrainingPlan(input = {}) {
  const goal = TRAINING_GOALS.includes(input.goal) ? input.goal : 'General match preparation';
  const level = PLAN_LEVELS.includes(input.level) ? input.level : 'Intermediate';
  const days = Math.max(1, Math.min(6, Number(input.days) || 3));
  const duration = [30, 45, 60, 75, 90].includes(Number(input.duration)) ? Number(input.duration) : 60;
  const weeks = PLAN_LENGTHS.includes(Number(input.weeks)) ? Number(input.weeks) : 1;
  const totalWeeks = weeks === 0 ? 1 : weeks;
  const sessionsPerWeek = weeks === 0 ? 1 : days;
  const analysisTags = Array.isArray(input.analysisTags) ? input.analysisTags : [];
  const wanted = new Set([goal, ...analysisTags]);
  const ranked = [...DRILL_LIBRARY].sort((a, b) => Number(b.tags.some(tag => wanted.has(tag))) - Number(a.tags.some(tag => wanted.has(tag))) || a.difficulty - b.difficulty);
  const sessions = [];
  for (let week = 1; week <= totalWeeks; week += 1) {
    const phase = planPhase(week, totalWeeks);
    for (let day = 1; day <= sessionsPerWeek; day += 1) {
      const technical = ranked[(week + day - 2) % Math.min(5, ranked.length)];
      const tactical = ranked[(week * 2 + day + 2) % ranked.length];
      const pressure = ranked.find(drill => drill.tags.includes(phase.startsWith('Pressure') ? 'Pressure points' : goal)) || ranked[(week + day + 5) % ranked.length];
      const warm = Math.max(5, Math.round(duration * 0.12));
      const cool = Math.max(4, Math.round(duration * 0.08));
      const movement = Math.max(6, Math.round(duration * 0.16));
      const pressureMinutes = Math.max(6, Math.round(duration * (week === totalWeeks ? 0.2 : 0.14)));
      const remaining = duration - warm - cool - movement - pressureMinutes;
      const technicalMinutes = Math.round(remaining * 0.56);
      const tacticalMinutes = remaining - technicalMinutes;
      const blocks = [
        { id: `w${week}d${day}-warm`, type: 'Warm-up', title: 'Dynamic court preparation', drill: 'Jog, side shuffle, crossover, split-step and progressive shadow swings.', target: 'Warm, balanced and pain-free.', minutes: warm, done: false },
        { id: `w${week}d${day}-technical`, type: 'Technical block', title: technical.name, drill: `${technical.setup}. ${technical.execution}.`, target: technical.objective, dose: drillDose(technical, technicalMinutes, phase, level), minutes: technicalMinutes, done: false },
        { id: `w${week}d${day}-movement`, type: 'Movement / footwork', title: 'Recovery triangle', drill: DRILL_LIBRARY[4].execution, target: DRILL_LIBRARY[4].objective, minutes: movement, done: false },
        { id: `w${week}d${day}-tactical`, type: 'Pattern / tactical block', title: tactical.name, drill: `${tactical.setup}. ${tactical.execution}.`, target: tactical.objective, dose: drillDose(tactical, tacticalMinutes, phase, level), minutes: tacticalMinutes, done: false },
        { id: `w${week}d${day}-pressure`, type: 'Pressure / competitive block', title: pressure.name, drill: pressure.execution, target: pressure.objective, minutes: pressureMinutes, done: false },
        { id: `w${week}d${day}-cool`, type: 'Cooldown / review', title: 'Reset and review', drill: 'Walk one lap, easy mobility, then note one repeatable cue and one adjustment.', target: 'Leave with one clear cue for the next session.', minutes: cool, done: false }
      ];
      sessions.push({ id: `week-${week}-day-${day}`, week, day, phase, duration, status: 'upcoming', blocks });
    }
  }
  return { id: `plan-${Date.now()}`, createdAt: new Date().toISOString(), goal, level, days, duration, weeks, sessions, source: analysisTags.length ? 'configuration + measured analysis' : 'configuration' };
}

function defaultPlanItems() {
  return generateTrainingPlan({ goal: 'General match preparation', level: 'Intermediate', days: 3, duration: 60, weeks: 1 }).sessions[0].blocks;
}

function visiblePlanItems() {
  const store = trainStore();
  return store.activePlan?.sessions?.[0]?.blocks || (store.plan.length ? store.plan : defaultPlanItems());
}

function validateVideoFile(file) {
  if (!file) return 'Choose a video first.';
  const ext = String(file.name || '').split('.').pop()?.toLowerCase() || '';
  if (!VIDEO_EXTENSIONS.includes(ext)) return 'Use MP4, MOV, M4V or WebM.';
  if (file.type && !VIDEO_MIME_TYPES.includes(file.type)) return 'That video type is not supported.';
  if (file.size > VIDEO_LIMIT_BYTES) return 'This clip is too large. Trim it under 80 MB for faster analysis.';
  return '';
}

const TRAIN_PAGES = new Set(['trainhome', 'today', 'analyze', 'train', 'learn', 'puzzles', 'profile']);
const PREDICT_PAGES = new Set(['predict', 'quant', 'players', 'compare', 'compete', 'simulation', 'model']);
const PRODUCT_LABELS = {
  train: 'Train',
  predict: 'Predict'
};

const MODEL_METRICS = {
  version: 'courtiq-real-20260809154449-enhanced_runtime_safe',
  dataRange: 'ATP artifact · training cutoff 2023 · held-out 2025 evaluation',
  matches: 78091,
  accuracy: '65.50%',
  auc: '0.7132',
  logLoss: '0.6185',
  brier: '0.2154',
  ece: '0.0271'
};

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
}

function normalizeKey(value) {
  return String(value || '').toLowerCase().replace(/[^a-z]/g, '');
}

const GEAR_COLORS = {
  babolat: '#3159ff',
  wilson: '#e23636',
  head: '#101713',
  yonex: '#21a45b',
  prince: '#43247d',
  dunlop: '#f4c11f',
  asics: '#285bcc',
  nike: '#111713',
  adidas: '#111713',
  tecnifibre: '#e33535',
  luxilon: '#8a8f98',
  solinco: '#7fd321',
  newbalance: '#c9162e',
  kswiss: '#174ea6',
  on: '#111713',
  volkl: '#f1c232',
  prokennex: '#2f6f4e',
  artengo: '#1574d4',
  diadem: '#7b42f6',
  lacoste: '#148547',
  gamma: '#f2b705'
};

function normalizeLegacyGearItem(item) {
  return {
    id: productKey(item),
    brand: item.brand,
    model: item.name,
    variant: '',
    category: item.type,
    subcategory: item.style || '',
    gender: 'unisex',
    image_url: item.imageUrl || '',
    image_local_path: item.imageLocalPath || '',
    image_verified: Boolean(item.imageVerified),
    product_url: item.productUrl || '',
    official_url: '',
    retailer_url: '',
    price: item.priceVerified ? item.price : null,
    currency: '',
    availability: 'unknown',
    status: 'unknown',
    active: true,
    specs: { summary: item.specs || '' },
    style: item.style || '',
    game_impact: item.impact || '',
    best_for: item.pro || '',
    source: 'CourtIQ legacy bootstrap seed',
    source_type: 'bootstrap_seed',
    source_links: [],
    last_verified: null
  };
}

function normalizeIndexedGearItem(item) {
  const legacy = item.name ? normalizeLegacyGearItem(item) : {};
  return {
    ...legacy,
    ...item,
    brand: item.brand || legacy.brand || '',
    model: item.model || item.name || legacy.model || '',
    variant: item.variant || legacy.variant || '',
    category: item.category || item.type || legacy.category || 'Accessory',
    specs: typeof item.specs === 'string' ? { summary: item.specs } : (item.specs || legacy.specs || {}),
    image_url: item.image_url || item.imageUrl || '',
    image_local_path: item.image_local_path || item.imageLocalPath || '',
    product_url: item.product_url || item.productUrl || '',
    official_url: item.official_url || '',
    retailer_url: item.retailer_url || '',
    game_impact: item.game_impact || item.impact || legacy.game_impact || '',
    best_for: item.best_for || item.pro || legacy.best_for || '',
    source_links: Array.isArray(item.source_links) ? item.source_links : []
  };
}

const BRAND_OFFICIAL_URLS = {
  Babolat: 'https://www.babolat.com/',
  Wilson: 'https://www.wilson.com/en-us/tennis',
  HEAD: 'https://www.head.com/en/tennis',
  Yonex: 'https://www.yonex.com/tennis',
  Tecnifibre: 'https://www.tecnifibre.com/',
  Dunlop: 'https://dunlopsports.com/tennis/',
  Prince: 'https://princetennis.com/',
  ASICS: 'https://www.asics.com/',
  Nike: 'https://www.nike.com/tennis',
  Adidas: 'https://www.adidas.com/tennis',
  Puma: 'https://us.puma.com/us/en/sports/tennis',
  'New Balance': 'https://www.newbalance.com/tennis/',
  'K-Swiss': 'https://kswiss.com/',
  On: 'https://www.on.com/',
  Solinco: 'https://www.solincosports.com/',
  Luxilon: 'https://www.luxilon.com/',
  Volkl: 'https://www.volkltennis.com/',
  ProKennex: 'https://prokennex.com/',
  Artengo: 'https://www.decathlon.com/',
  Diadem: 'https://diademsports.com/',
  Lacoste: 'https://www.lacoste.com/',
  Gamma: 'https://www.gammasports.com/'
};

function svgText(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

function svgUri(svg) {
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function gearName(item) {
  return [item.model || item.name, item.variant].filter(Boolean).join(' ').trim();
}

function gearCategory(item) {
  return item.category || item.type || 'Gear';
}

function gearTitle(item) {
  return `${item.brand || ''} ${gearName(item)}`.trim();
}

function productKey(item) {
  return String(item.id || `${item.brand} ${gearName(item)}`)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function gearProductImage(item) {
  if (item.image_local_path) return item.image_local_path;
  if (item.image_verified && item.image_url) return item.image_url;
  return '';
}

function gearMissingImageMarkup(item, hidden = false) {
  return `<div class="gear-photo-missing"${hidden ? ' hidden' : ''}>
    <span>Photo pending</span>
    <b>${escapeHtml(gearTitle(item))}</b>
    <small>Exact verified product image not stored yet.</small>
  </div>`;
}

function gearExtraVisualMarkup(item) {
  if (normalizeKey(gearCategory(item)) !== 'ball') return '';
  return `<span class="ball-can-visual" aria-hidden="true"></span><span class="loose-ball-visual" aria-hidden="true"></span>`;
}

const GEAR_PROFILE = {
  level: 'Competitive',
  targetWeight: 270,
  surface: 'Hard court',
  favoriteTypes: ['Racket', 'Shoes', 'String'],
  favoriteStyles: ['control', 'spin', 'speed', 'comfort', 'light', 'support'],
  preferredBrands: ['Prince', 'Babolat', 'Wilson', 'HEAD', 'Yonex']
};

function gearInterest() {
  try {
    return JSON.parse(localStorage.cqGearInterest || '{"brands":{},"types":{},"styles":{},"queries":[]}');
  } catch {
    return { brands: {}, types: {}, styles: {}, queries: [] };
  }
}

function saveGearInterest(interest) {
  localStorage.cqGearInterest = JSON.stringify(interest);
}

function rememberGearInterest(item, query = '') {
  const interest = gearInterest();
  if (item) {
    interest.brands[item.brand] = (interest.brands[item.brand] || 0) + 3;
    const category = gearCategory(item);
    interest.types[category] = (interest.types[category] || 0) + 2;
    String(`${item.style} ${item.game_impact || item.impact} ${item.best_for || item.pro}`).toLowerCase().split(/[^a-z0-9]+/).filter(Boolean).forEach(token => {
      if (['spin', 'control', 'power', 'comfort', 'speed', 'support', 'clay', 'hard', 'budget', 'advanced', 'light'].includes(token)) {
        interest.styles[token] = (interest.styles[token] || 0) + 1;
      }
    });
  }
  if (query && query.length > 1) {
    interest.queries = [query, ...(interest.queries || []).filter(saved => saved !== query)].slice(0, 8);
  }
  saveGearInterest(interest);
}

function gearSpecsSummary(specs) {
  if (!specs) return '';
  if (typeof specs === 'string') return specs;
  if (specs.summary) return specs.summary;
  const parts = [];
  if (specs.head_size_sq_in) parts.push(`${specs.head_size_sq_in} in²`);
  if (specs.unstrung_weight_g) parts.push(`${specs.unstrung_weight_g} g`);
  if (specs.string_pattern) parts.push(specs.string_pattern.replace('x', '×'));
  if (specs.gauge) parts.push(`${specs.gauge} gauge`);
  return parts.join(' · ');
}

function weightFromSpecs(specs) {
  const match = gearSpecsSummary(specs).match(/(\d{3})\s*g/);
  return match ? Number(match[1]) : null;
}

function gearScore(item, interest = gearInterest()) {
  const text = `${gearName(item)} ${item.subcategory || ''} ${item.style || ''} ${item.game_impact || item.impact || ''} ${gearSpecsSummary(item.specs)}`.toLowerCase();
  let score = 0;
  if (GEAR_PROFILE.preferredBrands.includes(item.brand)) score += 9;
  if (GEAR_PROFILE.favoriteTypes.includes(gearCategory(item))) score += 7;
  GEAR_PROFILE.favoriteStyles.forEach(style => {
    if (text.includes(style)) score += 4;
  });
  if (text.includes('competitive')) score += 5;
  if (text.includes('hard')) score += 3;
  const weight = weightFromSpecs(item.specs);
  if (weight) score += Math.max(0, 8 - Math.abs(weight - GEAR_PROFILE.targetWeight) / 5);
  score += (interest.brands?.[item.brand] || 0) * 2;
  score += (interest.types?.[gearCategory(item)] || 0) * 2;
  Object.entries(interest.styles || {}).forEach(([style, value]) => {
    if (text.includes(style)) score += value;
  });
  (interest.queries || []).forEach(query => {
    if (normalizeKey(`${item.brand} ${gearName(item)} ${item.style}`).includes(normalizeKey(query))) score += 6;
  });
  return score;
}

function sortedGearItems(items = GEAR_ITEMS) {
  const interest = gearInterest();
  return [...items].sort((a, b) => gearScore(b, interest) - gearScore(a, interest));
}

function gearRecommendationReason(item) {
  const weight = weightFromSpecs(item.specs);
  if (weight && Math.abs(weight - GEAR_PROFILE.targetWeight) <= 15) return `Close to your ${GEAR_PROFILE.targetWeight} g preference`;
  if (GEAR_PROFILE.preferredBrands.includes(item.brand)) return `${item.brand} matches your saved brand preference`;
  if (String(item.game_impact || item.impact).toLowerCase().includes('comfort')) return 'Comfort-focused option for regular training';
  if (String(item.game_impact || item.impact).toLowerCase().includes('spin')) return 'Good fit for a spin/control setup';
  return 'Recommended from your recent gear activity';
}

function gearPriceLabel(item) {
  if (item.price && item.last_verified) return item.currency ? `${item.currency} ${item.price}` : item.price;
  if (item.product_url || item.retailer_url) return 'See current price';
  return 'Price unavailable';
}

function gearSourceLinks(item) {
  return [item.product_url, item.official_url, item.retailer_url, ...(item.source_links || [])]
    .filter(Boolean)
    .filter((url, index, list) => list.indexOf(url) === index);
}

function gearSearchText(item) {
  return normalizeKey(`${item.brand} ${gearName(item)} ${gearCategory(item)} ${item.subcategory || ''} ${item.style || ''} ${item.game_impact || ''} ${item.best_for || ''} ${gearSpecsSummary(item.specs)}`);
}

function gearSearchScore(item, rawQuery = '') {
  const query = normalizeKey(rawQuery);
  if (!query) return 1;
  const name = normalizeKey(`${item.brand} ${gearName(item)}`);
  const text = gearSearchText(item);
  const tokens = query.split(/\s+/).filter(Boolean);
  if (query === name) return 1000;
  if (name.startsWith(query)) return 850;
  if (tokens.every(token => text.includes(token))) return 650 + tokens.length;
  if (text.includes(query)) return 450;
  const textTokens = text.split(/\s+/).filter(Boolean);
  if (tokens.length && tokens.every(token => Math.min(...textTokens.map(candidate => editDistance(token, candidate))) <= 2)) return 220;
  if (tokens.some(token => editDistance(token, name.slice(0, token.length + 3)) <= 2)) return 120;
  return 0;
}

function filterGearIndexItems({ query = '', type = 'All', brand = 'All brands' } = {}) {
  return REAL_GEAR_ITEMS
    .map(item => ({ item, score: gearSearchScore(item, query) }))
    .filter(entry => entry.score > 0)
    .filter(entry => type === 'All' || gearCategory(entry.item) === type)
    .filter(entry => brand === 'All brands' || entry.item.brand === brand)
    .sort((a, b) => b.score - a.score || gearScore(b.item) - gearScore(a.item))
    .map(entry => entry.item);
}

function paginateGearResults(items, page = state.gearPage || 1, pageSize = state.gearPageSize || 24) {
  const safePage = Math.max(1, Number(page) || 1);
  const safePageSize = Math.max(1, Math.min(96, Number(pageSize) || 24));
  return {
    items: items.slice(0, safePage * safePageSize),
    total: items.length,
    hasMore: safePage * safePageSize < items.length
  };
}

function gearCardMarkup(item, extraClass = '', note = '') {
  const image = gearProductImage(item);
  const itemType = String(gearCategory(item) || 'Gear');
  const detailLine = gearSpecsSummary(item.specs) || item.subcategory || itemType;
  const productUrl = item.product_url || item.official_url || item.retailer_url || '';
  const brandUrl = item.official_url || BRAND_OFFICIAL_URLS[item.brand] || '';
  const priceLabel = gearPriceLabel(item);
  const status = item.status && item.status !== 'unknown' ? item.status : '';
  return `<article class="gear-card product-card ${extraClass}" data-product-key="${escapeHtml(productKey(item))}" data-type="${escapeHtml(itemType)}" data-brand="${escapeHtml(item.brand)}">
    <div class="gear-visual visual-${normalizeKey(itemType)} brand-${normalizeKey(item.brand)} ${image ? 'has-product-photo' : 'needs-product-photo'}">
      ${image
        ? `<img class="gear-photo" src="${escapeHtml(image)}" alt="${escapeHtml(gearTitle(item) + ' product photo')}" loading="lazy" onerror="this.hidden=true;this.closest('.gear-visual').classList.remove('has-product-photo');this.closest('.gear-visual').classList.add('needs-product-photo');this.nextElementSibling.hidden=false;">${gearMissingImageMarkup(item, true)}`
        : gearMissingImageMarkup(item)}
      ${gearExtraVisualMarkup(item)}
      <span class="visual-brand">${escapeHtml(item.brand)}</span>
      <strong>${escapeHtml(gearName(item))}</strong>
    </div>
    <div class="product-top"><span class="eyebrow">${escapeHtml(itemType)}</span><b>${escapeHtml(priceLabel)}</b></div>
    <h2>${escapeHtml(gearTitle(item))}</h2>
    <p>${escapeHtml(detailLine)}</p>
    <p>${escapeHtml(item.game_impact || item.impact || item.best_for || 'Product details need source verification.')}</p>
    ${status ? `<small class="source-note">Status: ${escapeHtml(status)}</small>` : ''}
    ${note ? `<div class="recommendation-reason">${escapeHtml(note)}</div>` : ''}
    <div class="gear-actions">
      <button type="button" class="detail-btn" data-key="${escapeHtml(productKey(item))}">Details</button>
      <button type="button" class="store-btn" data-key="${escapeHtml(productKey(item))}" data-product="${escapeHtml(gearTitle(item))}">Find store</button>
      ${productUrl
        ? `<a class="official-link" target="_blank" rel="noopener noreferrer" href="${escapeHtml(productUrl)}">View Product ↗</a>`
        : brandUrl ? `<a class="official-link secondary-link" target="_blank" rel="noopener noreferrer" href="${escapeHtml(brandUrl)}">Visit ${escapeHtml(item.brand)} ↗</a>` : ''}
    </div>
  </article>`;
}

function editDistance(a, b) {
  a = normalizeKey(a);
  b = normalizeKey(b);
  if (!a || !b) return 99;

  const matrix = Array.from({ length: a.length + 1 }, (_, i) => Array(b.length + 1).fill(0));
  for (let i = 0; i <= a.length; i++) matrix[i][0] = i;
  for (let j = 0; j <= b.length; j++) matrix[0][j] = j;

  for (let i = 1; i <= a.length; i++) {
    for (let j = 1; j <= b.length; j++) {
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1)
      );
    }
  }

  return matrix[a.length][b.length];
}

function tourKey(value) {
  const raw = String(value || '').toUpperCase();
  if (raw === 'WTA' || raw === 'WOMEN') return 'WTA';
  return 'ATP';
}

function tourRosterKey(value) {
  return tourKey(value) === 'WTA' ? 'women' : 'men';
}

function playerRecord(name) {
  const key = normalizeKey(name);
  return DIRECTORY_PLAYERS.find(player => normalizeKey(player.name) === key) || null;
}

function abbreviatedNameCandidates(value) {
  const parts = String(value || '').trim().split(/\s+/).map(part => part.replace(/[,.]/g, '')).filter(Boolean);
  if (parts.length < 2) return [];
  const first = parts[0];
  const last = parts[parts.length - 1];
  if (!first || !last) return [];
  return [`${last} ${first[0]}.`, `${last}, ${first[0]}.`];
}

function rosterNameMatchesQuery(name, query) {
  const key = normalizeKey(name);
  if (!query) return true;
  if (key === query || key.startsWith(query) || key.includes(query)) return true;
  return abbreviatedNameCandidates(query).some(candidate => normalizeKey(candidate) === key);
}

function sortedDirectoryForTour(tour) {
  const key = tourKey(tour);
  const directory = DIRECTORY_BY_TOUR[key] || [];
  if (!directory.length) return [];
  return [...directory].sort((a, b) => {
    const aRank = Number(a.ranking || 99999);
    const bRank = Number(b.ranking || 99999);
    if (aRank !== bRank) return aRank - bRank;
    return String(a.name).localeCompare(String(b.name));
  });
}

function rosterFor(tour) {
  const key = tourKey(tour);
  const directory = sortedDirectoryForTour(key);
  if (directory.length) return directory.map(player => player.name);
  return ROSTERS[tourRosterKey(key)];
}

function titleLabel(value) {
  return String(value || '')
    .replace(/_/g, ' ')
    .replace(/\belo\b/ig, 'Elo')
    .replace(/\b\w/g, letter => letter.toUpperCase());
}

function surfaceMetricLabel(surface) {
  return `${titleLabel(surface)} Elo`;
}

function resolvePlayerName(value, tour = state.selectedTour) {
  const query = normalizeKey(value);
  if (query.length < 2) return '';
  const roster = rosterFor(tour);

  return roster.find(name => normalizeKey(name) === query)
    || abbreviatedNameCandidates(value).map(candidate => roster.find(name => normalizeKey(name) === normalizeKey(candidate))).find(Boolean)
    || roster.find(name => normalizeKey(name).startsWith(query) || query.startsWith(normalizeKey(name)))
    || roster.find(name => normalizeKey(name).includes(query))
    || roster
      .map(name => [name, editDistance(query, normalizeKey(name))])
      .filter(([, distance]) => distance <= 2)
      .sort((a, b) => a[1] - b[1])[0]?.[0]
    || '';
}

function inferTourFromText(value) {
  const query = normalizeKey(value);
  if (query.length < 2) return '';
  const matches = ['ATP', 'WTA'].filter(tour => rosterFor(tour).some(name => {
    return rosterNameMatchesQuery(name, query);
  }));
  return matches.length === 1 ? matches[0] : '';
}

function playerTour(name) {
  const record = playerRecord(name);
  if (record) return record.tour === 'WTA' ? 'women' : 'men';
  return ROSTERS.women.includes(name) ? 'women' : 'men';
}

function playerTourKey(name) {
  return playerTour(name) === 'women' ? 'WTA' : 'ATP';
}

function oppositeSlot(slot) {
  return slot === 'player1' ? 'player2' : 'player1';
}

function fallbackPlayer(tour, excludedName) {
  return rosterFor(tour).find(name => name !== excludedName) || rosterFor(tour)[0];
}

function keepValidMatchup(changedSlot = 'player1') {
  state.selectedTour = tourKey(state.selectedTour);
  if (playerRecord(state.player1)) state.selectedTour = playerTourKey(state.player1);
  if (changedSlot === 'player2' && playerRecord(state.player2)) state.selectedTour = playerTourKey(state.player2);

  const roster = rosterFor(state.selectedTour);
  if (!roster.includes(state.player1)) state.player1 = fallbackPlayer(state.selectedTour, state.player2);
  if (!roster.includes(state.player2)) state.player2 = fallbackPlayer(state.selectedTour, state.player1);

  if (playerTour(state.player1) !== playerTour(state.player2)) {
    if (changedSlot === 'player2') {
      state.selectedTour = playerTourKey(state.player2);
      state.player1 = fallbackPlayer(state.selectedTour, state.player2);
    } else {
      state.selectedTour = playerTourKey(state.player1);
      state.player2 = fallbackPlayer(state.selectedTour, state.player1);
    }
  }

  if (state.player1 === state.player2) {
    state.player2 = fallbackPlayer(state.selectedTour, state.player1);
  }
}

function saveState() {
  keepValidMatchup();
  localStorage.cqP1 = state.player1;
  localStorage.cqP2 = state.player2;
  localStorage.cqTour = state.selectedTour;
  localStorage.cqProduct = state.product;
  const route = normalizeRoute(state.route || state.page);
  if (route.product === 'train') localStorage.cqLastTrainRoute = route.id;
  if (route.product === 'predict') localStorage.cqLastPredictRoute = route.id;
  state.draftP1 = state.player1;
  state.draftP2 = state.player2;
  localStorage.cqSlam = state.slam;
  localStorage.cqPuzzleId = state.puzzleId;
  localStorage.cqPuzzleSeed = state.puzzleSeed;
  localStorage.cqPuzzleStep = state.puzzleStep;
  localStorage.cqPuzzleCategory = state.puzzleCategory;
  localStorage.cqPuzzleDifficulty = state.puzzleDifficulty;
  localStorage.cqPuzzleSurface = state.puzzleSurface;
  localStorage.cqPuzzleStats = JSON.stringify(state.puzzleStats || { attempted: 0, correct: 0, categories: {} });
}

function productForPage(page) {
  const route = ROUTE_BY_PAGE.get(page) || normalizeRoute(page);
  if (route.product === 'train' || route.product === 'predict') return route.product;
  if (PREDICT_PAGES.has(page)) return 'predict';
  if (TRAIN_PAGES.has(page)) return 'train';
  return state.product || 'train';
}

function syncHash(route, replace = false) {
  const nextHash = `#${route.id}`;
  if (location.hash === nextHash) return false;
  if (replace) {
    history.replaceState(null, '', nextHash);
    return false;
  }
  location.hash = route.id;
  return true;
}

function applyRoute(value, options = {}) {
  const route = normalizeRoute(value);
  if (!options.force && route.id === state.route && location.hash === `#${route.id}`) {
    return;
  }
  state.route = route.id;
  state.page = route.page;
  state.product = route.product === 'entry' ? (state.product || localStorage.cqProduct || 'train') : route.product;
  saveState();
  const renderPendingFromHashChange = syncHash(route, Boolean(options.replace));
  if (!renderPendingFromHashChange) render();
}

function setProduct(product, preferredRoute = '') {
  const nextProduct = product === 'predict' ? 'predict' : 'train';
  const preferred = preferredRoute ? normalizeRoute(preferredRoute) : savedRouteForProduct(nextProduct);
  const route = preferred.product === nextProduct ? preferred : defaultRouteForProduct(nextProduct);
  state.product = nextProduct;
  applyRoute(route.id);
}

function goToPage(value) {
  applyRoute(value);
}

function handleRouteIntent(event) {
  const target = event.target.closest('button[data-route], button[data-page], button[data-product]');
  if (!target) return;

  if (target.dataset.route) {
    event.preventDefault();
    setProduct(target.dataset.product, target.dataset.route);
    return;
  }

  if (target.dataset.page) {
    event.preventDefault();
    goToPage(target.dataset.page);
    return;
  }

  if (target.dataset.product === 'train' || target.dataset.product === 'predict') {
    event.preventDefault();
    setProduct(target.dataset.product);
  }
}

function toast(message) {
  const element = $('#toast');
  element.textContent = message;
  element.classList.add('show');
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => element.classList.remove('show'), 1600);
}

function processingMarkup(title, steps) {
  return `<article class="processing-card">
    <div class="processing-orb"></div>
    <div>
      <span class="eyebrow">PROCESSING</span>
      <h2>${escapeHtml(title)}</h2>
      <div class="processing-steps">
        ${steps.map((step, index) => `<span class="${index === 0 ? 'active' : 'pending'}"><b>${String(index + 1).padStart(2, '0')}</b>${escapeHtml(step)}</span>`).join('')}
      </div>
    </div>
  </article>`;
}

function demoSeedFromName(name) {
  let value = 0;
  for (const character of name) value = (value * 31 + character.charCodeAt(0)) % 9973;
  return value;
}

function playerProfile(name) {
  if (skillCache.has(name)) return skillCache.get(name);

  const realProfile = PLAYER_STATS[name];
  if (realProfile) {
    const profile = {
      hard: realProfile.hard ?? realProfile.surfaceHard ?? 0,
      clay: realProfile.clay ?? realProfile.surfaceClay ?? 0,
      grass: realProfile.grass ?? realProfile.surfaceGrass ?? 0,
      serve: realProfile.servePointWon ?? realProfile.serve ?? 64,
      return: realProfile.returnPointWon ?? realProfile.return ?? 36,
      form: realProfile.recentForm ?? realProfile.form ?? 50,
      pressure: realProfile.pressure ?? realProfile.breakPointPerformance ?? 50,
      movement: realProfile.movement ?? 50,
      rally: realProfile.rallyTolerance ?? realProfile.rally ?? 50,
      fatigue: realProfile.fatigue ?? 8,
      volatility: realProfile.volatility ?? 10,
      source: 'historical'
    };
    skillCache.set(name, profile);
    return profile;
  }

  const record = playerRecord(name);
  if (record?.status === 'trained') {
    const profile = {
      hard: record.hard_elo ?? 0,
      clay: record.clay_elo ?? 0,
      grass: record.grass_elo ?? 0,
      serve: record.serve_point_won ?? 0,
      return: record.return_point_won ?? 0,
      form: record.form_5 ?? 0,
      pressure: 0,
      movement: 0,
      rally: 0,
      fatigue: 0,
      volatility: 0,
      source: 'directory'
    };
    skillCache.set(name, profile);
    return profile;
  }
  if (record?.status === 'model_untrained') {
    const profile = {
      hard: 0,
      clay: 0,
      grass: 0,
      serve: 0,
      return: 0,
      form: 0,
      pressure: 0,
      movement: 0,
      rally: 0,
      fatigue: 0,
      volatility: 0,
      source: 'unavailable'
    };
    skillCache.set(name, profile);
    return profile;
  }

  const seed = demoSeedFromName(name);
  const base = playerTour(name) === 'women' ? 74 : 76;
  const profile = {
    hard: base + seed % 16,
    clay: base + (seed * 3) % 16,
    grass: base + (seed * 7) % 16,
    serve: 58 + seed % 26,
    return: 54 + (seed * 5) % 28,
    form: 60 + (seed * 11) % 35,
    pressure: 58 + (seed * 13) % 34,
    movement: 56 + (seed * 17) % 34,
    rally: 55 + (seed * 19) % 35,
    fatigue: 4 + (seed * 23) % 18,
    volatility: 6 + (seed * 29) % 16,
    source: 'demo'
  };

  skillCache.set(name, profile);
  return profile;
}

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function sigmoid(value) {
  return 1 / (1 + Math.exp(-value));
}

function percent(value) {
  return Math.round(clamp(value, 2, 98) * 10) / 10;
}

function selectedSlam() {
  const surfaceContext = { 'Hard Court': 'Hard', 'Clay Court': 'Clay', 'Grass Court': 'Grass' };
  if (surfaceContext[state.slam]) return { name: state.slam, surface: surfaceContext[state.slam] };
  return GRAND_SLAMS.find(item => item.name === state.slam) || GRAND_SLAMS[2];
}

function gameWinProbability(pointProbability) {
  const p = clamp(pointProbability, 0.01, 0.99);
  const q = 1 - p;
  const beforeDeuce = (p ** 4) * (1 + 4 * q + 10 * (q ** 2));
  const reachDeuce = 20 * (p ** 3) * (q ** 3);
  const winFromDeuce = (p ** 2) / ((p ** 2) + (q ** 2));
  return beforeDeuce + reachDeuce * winFromDeuce;
}

function setWinProbability(holdA, holdB) {
  const breakEdge = (holdA - (1 - holdB));
  const returnEdge = ((1 - holdB) - (1 - holdA));
  return sigmoid((breakEdge * 3.2) + (returnEdge * 1.1));
}

function matchWinFromSet(setProbability, bestOf = 3) {
  const p = clamp(setProbability, 0.01, 0.99);
  if (bestOf === 5) {
    return (p ** 3) * (1 + 3 * (1 - p) + 6 * ((1 - p) ** 2));
  }
  return (p ** 2) * (3 - 2 * p);
}

function buildPrediction() {
  keepValidMatchup();

  const slam = selectedSlam();
  const surfaceKey = slam.surface.toLowerCase();
  const first = playerProfile(state.player1);
  const second = playerProfile(state.player2);
  const surfaceSpeed = slam.surface === 'Grass' ? 0.06 : slam.surface === 'Clay' ? -0.04 : 0.02;
  const usingHistorical = first.source === 'historical' && second.source === 'historical';
  const ratingBase = usingHistorical ? 0 : 1520;
  const ratingScale = usingHistorical ? 1 : 8;
  const firstElo = ratingBase + first[surfaceKey] * ratingScale + first.form * 1.9 + first.pressure * 1.3 - first.fatigue * 3;
  const secondElo = ratingBase + second[surfaceKey] * ratingScale + second.form * 1.9 + second.pressure * 1.3 - second.fatigue * 3;
  const eloPrior = sigmoid((firstElo - secondElo) / 315);
  const firstServePoint = sigmoid(-0.08 + surfaceSpeed + (first.serve - second.return) / 58 + (first.pressure - second.pressure) / 210);
  const secondServePoint = sigmoid(-0.08 + surfaceSpeed + (second.serve - first.return) / 58 + (second.pressure - first.pressure) / 210);
  const firstHold = gameWinProbability(firstServePoint);
  const secondHold = gameWinProbability(secondServePoint);
  const setProb = setWinProbability(firstHold, secondHold);
  const bestOf = playerTour(state.player1) === 'men' ? 5 : 3;
  const markovMatch = matchWinFromSet(setProb, bestOf);
  const pressureSwing = sigmoid((first.pressure - second.pressure + first.rally - second.rally - first.volatility + second.volatility) / 80);
  const movementSwing = sigmoid((first.movement - second.movement - first.fatigue + second.fatigue) / 70);
  const blended = (markovMatch * 0.56) + (eloPrior * 0.24) + (pressureSwing * 0.12) + (movementSwing * 0.08);
  const firstChance = percent(blended * 100);
  const firstIsWinner = firstChance >= 50;
  const projectedScore = bestOf === 5
    ? (firstIsWinner ? (firstChance > 68 ? '3–1' : '3–2') : (firstChance < 32 ? '1–3' : '2–3'))
    : (firstIsWinner ? (firstChance > 68 ? '2–0' : '2–1') : (firstChance < 32 ? '0–2' : '1–2'));

  return {
    winner: firstIsWinner ? state.player1 : state.player2,
    winnerChance: firstIsWinner ? firstChance : percent(100 - firstChance),
    firstChance,
    slam,
    first,
    second,
    firstElo: Math.round(firstElo),
    secondElo: Math.round(secondElo),
    firstHold: percent(firstHold * 100),
    secondHold: percent(secondHold * 100),
    firstBreak: percent((1 - secondHold) * 100),
    secondBreak: percent((1 - firstHold) * 100),
    bestOf,
    projectedScore,
    edge: Math.abs(Math.round((firstChance - 50) * 10) / 10),
    usingHistorical
  };
}

function listTourForActiveSlot() {
  return state.selectedTour;
}

function visiblePlayers() {
  const query = state.search.trim();
  const roster = rosterFor(listTourForActiveSlot());
  if (!query) return roster.slice(0, 40);

  const resolved = resolvePlayerName(query, listTourForActiveSlot());
  const queryKey = normalizeKey(query);

  const exact = roster.filter(name => normalizeKey(name) === queryKey || name === resolved);
  const prefix = roster.filter(name => !exact.includes(name) && rosterNameMatchesQuery(name, queryKey) && normalizeKey(name).startsWith(queryKey));
  const contains = roster.filter(name => !exact.includes(name) && !prefix.includes(name) && rosterNameMatchesQuery(name, queryKey));
  const fuzzy = roster
    .filter(name => !exact.includes(name) && !prefix.includes(name) && !contains.includes(name))
    .map(name => [name, editDistance(queryKey, normalizeKey(name))])
    .filter(([, distance]) => distance <= 2)
    .sort((a, b) => a[1] - b[1])
    .map(([name]) => name);

  return [...exact, ...prefix, ...contains, ...fuzzy].slice(0, 60);
}

function selectPlayer(name, slot = state.activeSlot) {
  if (!name) return;

  state[slot] = name;
  state.backendPrediction = null;
  state.predictionError = '';
  if (slot === 'player1') state.draftP1 = name;
  if (slot === 'player2') state.draftP2 = name;
  keepValidMatchup(slot);
  state.draftP1 = state.player1;
  state.draftP2 = state.player2;
  state.activeSlot = oppositeSlot(slot);
  state.search = '';
  saveState();
  render();
}

function commitField(slot) {
  const input = slot === 'player1' ? $('#p1') : $('#p2');
  const typedValue = input?.value || state[slot];
  const resolved = resolvePlayerName(typedValue, state.selectedTour);

  if (!resolved) {
    toast(`No current player found for "${typedValue}". Pick from the list.`);
    return false;
  }

  state[slot] = resolved;
  state.backendPrediction = null;
  state.predictionError = '';
  if (slot === 'player1') state.draftP1 = resolved;
  if (slot === 'player2') state.draftP2 = resolved;
  keepValidMatchup(slot);
  state.draftP1 = state.player1;
  state.draftP2 = state.player2;
  saveState();
  return true;
}

function apiUrl(path) {
  return apiClient.url(path);
}

function readableApiError(error) {
  const message = String(error?.message || error || '');
  if (message.includes('Failed to fetch') || message.includes('NetworkError')) {
    return `CourtIQ's prediction service is temporarily unavailable.`;
  }
  return message || 'Prediction engine is unavailable.';
}

async function apiFetchJson(path, options = {}) {
  return apiClient.json(path, options);
}

async function checkBackendHealth() {
  return apiFetchJson('/api/health');
}

async function runBackendPrediction() {
  const payload = await apiFetchJson('/api/predict', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      player1: state.player1,
      player2: state.player2,
      event: state.slam,
      tour: state.selectedTour.toLowerCase()
    })
  });
  return payload;
}

function handleTopInput(slot, value) {
  state.activeSlot = slot;
  const inferredTour = inferTourFromText(value);
  if (inferredTour && inferredTour !== state.selectedTour) {
    state.selectedTour = inferredTour;
    state[oppositeSlot(slot)] = fallbackPlayer(inferredTour, value);
  }
  state.search = value;
  state.backendPrediction = null;
  state.predictionError = '';
  if (slot === 'player1') state.draftP1 = value;
  if (slot === 'player2') state.draftP2 = value;

  updatePlayerResults();
}

function pageHeader(section, title, copy) {
  return `<div class="hero">
    <span class="eyebrow">${section}</span>
    <h1>${title}</h1>
    <p>${copy}</p>
  </div>`;
}

function playerRow(name) {
  const safeName = escapeHtml(name);
  const record = playerRecord(name);
  const profile = playerProfile(name);
  const serveScore = Math.round(profile.serve || 0);
  const meta = record?.status === 'model_untrained'
    ? `${record.tour} · Profile only`
    : `${record?.tour || (playerTour(name) === 'women' ? 'WTA' : 'ATP')} · ${surfaceEloText(record, profile)} · Serve ${serveScore || '—'}`;
  return `<div class="row">
    <button data-name="${safeName}">
      <strong>${safeName}</strong>
      <em class="tag">${meta}</em>
    </button>
    <span>
      <button data-name="${safeName}" data-force="player1">P1</button>
      <button data-name="${safeName}" data-force="player2">P2</button>
    </span>
  </div>`;
}

function honestElo(value) {
  return Number.isFinite(Number(value)) && Number(value) > 0 ? Math.round(Number(value)) : '—';
}

function surfaceEloText(record, profile = {}) {
  return `Hard ${honestElo(record?.hard_elo ?? profile.hard)} · Clay ${honestElo(record?.clay_elo ?? profile.clay)} · Grass ${honestElo(record?.grass_elo ?? profile.grass)}`;
}

function playerResultsHtml() {
  const rows = visiblePlayers().map(playerRow).join('');
  return rows || `<div class="empty">No current player found. Try a shorter name.</div>`;
}

function backendPredictionMarkup() {
  if (state.predictionLoading) {
    return `<div class="result empty-result" id="prediction-result">
      ${processingMarkup('Running Match Predictor', [
        'Checking backend health',
        'Loading trained model artifact',
        'Scoring matchup features',
        'Rendering forecast'
      ])}
    </div>`;
  }
  if (state.predictionError) {
    return `<div class="result error-result" id="prediction-result">
      <div>
        <span>Forecast paused</span>
        <h2>Prediction engine is not ready</h2>
        <small>${escapeHtml(state.predictionError)}</small>
        <button id="retry-predict" class="ghost-action">Retry</button>
      </div>
    </div>`;
  }
  if (!state.backendPrediction) {
    return `<div class="result empty-result" id="prediction-result">
      <div>
        <span>READY</span>
        <h2>Run CourtIQ</h2>
        <small>Your forecast, matchup stats and model notes appear here.</small>
      </div>
    </div>`;
  }
  const prediction = state.backendPrediction;
  const chance = Math.round(Number(prediction.player1_win_probability || 0) * 1000) / 10;
  const winnerChance = prediction.winner === prediction.player1 ? chance : Math.round((100 - chance) * 10) / 10;
  return `<div class="result forecast-result" id="prediction-result">
    <section class="winner-block">
      <span>COURTIQ FORECAST</span>
      <h2>${escapeHtml(prediction.winner)}</h2>
      <small>${winnerChance >= 60 ? 'Clear edge' : winnerChance >= 54 ? 'Small edge' : 'Near coin-flip'}</small>
    </section>
    <section class="forecast-report">
      ${forecastBar(chance)}
      <div class="model-version">${escapeHtml(prediction.model_version || MODEL_METRICS.version)}</div>
    </section>
  </div>`;
}

function backendMetricCards() {
  const prediction = state.backendPrediction;
  if (!prediction) return '';
  const features = prediction.features || {};
  const p1Chance = Math.round(Number(prediction.player1_win_probability || 0) * 1000) / 10;
  return `<section class="grid">
    ${[
      ['P1 chance', `${p1Chance}%`],
      ['Surface Elo', `${features.p1_surface_elo ?? '—'} / ${features.p2_surface_elo ?? '—'}`],
      ['Hold edge', `${Math.round(Number(features.p1_hold || 0) * 1000) / 10}% / ${Math.round(Number(features.p2_hold || 0) * 1000) / 10}%`],
      ['Best of', `${features.best_of ?? '—'}`]
    ].map(([label, value]) => `<article class="stat"><small>${label}</small><b>${value}</b></article>`).join('')}
  </section>`;
}

function tourSelectorMarkup() {
  return `<div class="tour-switch" role="group" aria-label="Tour selector">
    ${['ATP', 'WTA'].map(tour => `<button type="button" data-tour="${tour}" class="${state.selectedTour === tour ? 'active' : ''}">${tour}</button>`).join('')}
  </div>`;
}

function entryPage() {
  return `<section class="entry-screen">
    <div class="entry-brand">
      <span class="ball"></span>
      <div><b>COURTIQ</b><small>Tennis intelligence system</small></div>
    </div>
    <div class="entry-grid">
      <article class="entry-panel train-panel" data-product-card="train">
        <div class="court-geometry train-geometry" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
        <span class="eyebrow">Personal development</span>
        <h1>TRAIN</h1>
        <p>Improve your game with measured video analysis, structured practice plans, visual learning and tactical decision training.</p>
        <div class="entry-shortcuts">
          <button type="button" data-page="train/analyze">Pose-based movement analysis</button>
          <button type="button" data-page="train/plan">Drills + practice plans</button>
          <button type="button" data-page="train/puzzles">Puzzle Court decisions</button>
        </div>
        <button data-product="train" data-route="train/overview">Enter Train</button>
      </article>
      <article class="entry-panel predict-panel" data-product-card="predict">
        <div class="court-geometry predict-geometry" aria-hidden="true"><i></i><i></i><i></i><i></i></div>
        <span class="eyebrow">Professional analytics</span>
        <h1>PREDICT</h1>
        <p>Forecast matchups with the trained model, compare players, inspect Elo-style signals and run tournament simulations.</p>
        <div class="entry-shortcuts">
          <button type="button" data-page="predict/match">Win probability</button>
          <button type="button" data-page="predict/compare">Surface strength</button>
          <button type="button" data-page="predict/simulation">Simulation</button>
          <button type="button" data-page="predict/model-lab">Model lab</button>
        </div>
        <button data-product="predict" data-route="predict/overview">Enter Predict</button>
      </article>
    </div>
  </section>`;
}

function trainOverviewPage() {
  const store = trainStore();
  const latest = store.analyses[0];
  const plan = visiblePlanItems();
  const todaySession = store.sessions[0];
  const nextPlanSession = store.activePlan?.sessions?.find(item => item.status !== 'completed') || store.activePlan?.sessions?.[0];
  const sessionTitle = nextPlanSession?.phase || (latest?.recommendations?.[0]?.title ?? 'Foundation session');
  const sessionMinutes = nextPlanSession?.duration || plan.reduce((sum, item) => sum + Number(item.minutes || 0), 0);
  return `<section class="train-dashboard">
    <article class="train-hero-panel">
      <span class="eyebrow">TRAIN</span>
      <h1>Your tennis performance room.</h1>
      <p>Upload a clip, turn measured observations into a practice plan, and keep learning tools one step away.</p>
      <div class="hero-actions">
        <button class="primary-action" data-page="train/analyze">Analyze video</button>
        <button class="ghost-action" data-page="train/plan">Open training plan</button>
      </div>
    </article>
    <article class="train-panel-card wide">
      <div class="section-head">
        <div><span class="eyebrow">NEXT SESSION</span><h2>${escapeHtml(sessionTitle)}</h2><p class="session-meta">${sessionMinutes ? `${sessionMinutes} min · ` : ''}${Math.min(plan.length, 4)} blocks</p></div>
        <button class="ghost-action" data-page="train/plan">Edit plan</button>
      </div>
      <div class="plan-preview">
        ${plan.slice(0, 4).map((item, index) => `<div class="plan-preview-row ${item.done ? 'done' : ''}">
          <span>${String(index + 1).padStart(2, '0')}</span>
          <div><b>${escapeHtml(item.title)}</b><small>${escapeHtml(item.target)}</small></div>
        </div>`).join('')}
      </div>
    </article>
    <article class="train-panel-card">
      <span class="eyebrow">RECENT WORK</span>
      ${latest ? `<h2>${escapeHtml(latest.filename)}</h2><p>${escapeHtml(new Date(latest.createdAt).toLocaleString())}</p><button class="ghost-action" data-page="train/analyze">Review analysis flow</button>` : `<h2>No clip analyzed yet</h2><p>Start with an 8–20 second clip. Raw video is sent only for processing and not saved in this local interface.</p><button class="ghost-action" data-page="train/analyze">Upload clip</button>`}
      ${todaySession ? `<p><b>Last session:</b> ${escapeHtml(todaySession.status)} · ${escapeHtml(todaySession.note || 'No note')}</p>` : ''}
    </article>
    <section class="train-support-grid">
      <article data-page="train/learn"><span>Learn</span><b>Visual stroke lessons</b><small>Body/court pictures before text.</small></article>
      <article data-page="train/puzzles"><span>Puzzle Court</span><b>Tactical decisions</b><small>Interactive rally situations.</small></article>
    </section>
  </section>`;
}

function forecastBar(p1Chance) {
  const p2Chance = Math.round((100 - p1Chance) * 10) / 10;
  return `<div class="forecast-bar" style="--p:${p1Chance}%">
    <div class="forecast-names"><b>${escapeHtml(state.player1)}</b><b>${escapeHtml(state.player2)}</b></div>
    <div class="forecast-track"><span></span><i></i></div>
    <div class="forecast-numbers"><b>${p1Chance}%</b><b>${p2Chance}%</b></div>
  </div>`;
}

function predictOverviewPage() {
  const p = state.backendPrediction;
  const p1Chance = p ? Math.round(Number(p.player1_win_probability || 0) * 1000) / 10 : 51.1;
  return `<section class="product-hero predict-product">
      <span class="eyebrow">PREDICT</span>
      <h1>Professional tennis intelligence.</h1>
      <p>Real-data forecasts, transparent model metrics and simulation tools for tournament-level questions.</p>
    </section>
    <section class="predict-home-grid">
      <article class="featured-match">
        <span class="eyebrow">FEATURED MATCHUP</span>
        <h2>${escapeHtml(state.player1)} vs ${escapeHtml(state.player2)}</h2>
        ${forecastBar(p1Chance)}
        <button class="primary-action" data-page="predict/match">Run full analysis</button>
      </article>
      <article class="map-card" data-page="predict/tournaments"><span>LIVE</span><h2>Verified prediction feed</h2><p>Upcoming matches grouped by tournament when schedule-backed data is available.</p></article>
      <article class="map-card" data-page="predict/simulation"><span>SIM</span><h2>Tournament simulation</h2><p>Run bracket-style projections from the production predictor.</p></article>
      <article class="map-card" data-page="predict/players"><span>ATP</span><h2>Player search</h2><p>Search active players and compare surface strengths.</p></article>
    </section>`;
}

function playersPage() {
  const names = state.search ? visiblePlayers() : rosterFor(state.selectedTour).slice(0, 60);
  return `${pageHeader('PLAYERS', 'Search player profiles.', 'Find players from the trained player directory and open a prediction or comparison without scrolling through a huge list.')}
    <section class="player-directory">
      ${tourSelectorMarkup()}
      <input id="finder" autocomplete="off" value="${escapeHtml(state.search)}" placeholder="Search player name…">
      <div class="results">${names.map(playerRow).join('')}</div>
    </section>`;
}

function comparePage() {
  keepValidMatchup();
  const first = playerProfile(state.player1);
  const second = playerProfile(state.player2);
  const surface = selectedSlam().surface.toLowerCase();
  return `${pageHeader('COMPARE', `${state.player1} vs ${state.player2}`, 'Compare transferable strengths without claiming impossible certainty.')}
    ${tourSelectorMarkup()}
    <section class="comparison-board">
      ${['hard', 'clay', 'grass', 'serve', 'return'].map(key => {
        const a = Math.round(first[key] || 0);
        const b = Math.round(second[key] || 0);
        const label = ['hard', 'clay', 'grass'].includes(key) ? surfaceMetricLabel(key) : titleLabel(key);
        return `<article><span>${escapeHtml(label)}</span>
          <b>${a}</b><div class="dual-meter" style="--a:${clamp(a, 0, 100)}%;--b:${clamp(b, 0, 100)}%"><i></i><em></em></div><b>${b}</b></article>`;
      }).join('')}
    </section>`;
}

function simulationPage() {
  const tour = playerTour(state.player1);
  const field = rosterFor(tour).slice(0, 12).map(name => {
    const profile = playerProfile(name);
    const surface = selectedSlam().surface.toLowerCase();
    return [name, Math.round((profile[surface] || 70) + profile.form * 0.4 + profile.serve * 0.2)];
  }).sort((a, b) => b[1] - a[1]);
  const top = field[0]?.[1] || 1;
  return `${pageHeader('SIMULATION', 'Tournament projection.', 'A bracket-ready view for the selected tour and Grand Slam surface.')}
    ${tourSelectorMarkup()}
    <section class="simulation-board">
      <article class="sim-control"><span class="eyebrow">${escapeHtml(selectedSlam().name)}</span><h2>${PRODUCT_LABELS.predict} simulation</h2><p>Uses the same player records available to the app. Start with matchup predictions, then expand into full bracket runs.</p><button id="run-sim" class="primary-action">Run simulation</button></article>
      <article class="champion-list">
        <span class="eyebrow">CHAMPION PROBABILITY</span>
        ${field.slice(0, 8).map(([name, score], index) => {
          const chance = Math.max(4, Math.round((score / field.reduce((sum, item) => sum + item[1], 0)) * 1000) / 10);
          return `<div><b>${index + 1}. ${escapeHtml(name)}</b><span>${chance}%</span><i style="width:${Math.round((score / top) * 100)}%"></i></div>`;
        }).join('')}
      </article>
    </section>`;
}

function modelPage() {
  return `${pageHeader('MODEL LAB', 'How CourtIQ predicts.', 'Transparent performance, real split boundaries and model quality without pretending every forecast is certain.')}
    <section class="model-lab">
      <article class="model-terminal">
        <span class="eyebrow">PRODUCTION MODEL</span>
        <h2>${MODEL_METRICS.version}</h2>
        <p>${MODEL_METRICS.dataRange}</p>
        <div class="metric-wall">
          <b><small>Matches</small>${MODEL_METRICS.matches.toLocaleString()}</b>
          <b><small>Accuracy</small>${MODEL_METRICS.accuracy}</b>
          <b><small>ROC-AUC</small>${MODEL_METRICS.auc}</b>
          <b><small>Log loss</small>${MODEL_METRICS.logLoss}</b>
          <b><small>Brier</small>${MODEL_METRICS.brier}</b>
          <b><small>ECE</small>${MODEL_METRICS.ece}</b>
        </div>
      </article>
      <article class="calibration-card">
        <span class="eyebrow">CALIBRATION</span>
        <div class="calibration-chart" aria-label="Calibration chart"><i></i><b></b><em></em></div>
        <p>Evaluation is chronological: training through 2023, calibration on 2024, untouched final test on 2025.</p>
      </article>
    </section>`;
}

function quantPage() {
  keepValidMatchup();
  const p1Value = escapeHtml(state.draftP1 ?? state.player1);
  const p2Value = escapeHtml(state.draftP2 ?? state.player2);

  const p1Profile = playerProfile(state.player1);
  const p2Profile = playerProfile(state.player2);
  const surface = selectedSlam().surface.toLowerCase();

  return `${pageHeader('MATCH PREDICTOR', 'Run the CourtIQ forecast.', 'Select two players from the same tour and a supported surface context, then run the production model.')}
    <section class="predictor">
      ${tourSelectorMarkup()}
      <div class="matchup-title">
        <div><span>Player A</span><b>${escapeHtml(state.player1)}</b><small>${p1Profile.source === 'unavailable' ? 'Profile only' : surfaceEloText(playerRecord(state.player1), p1Profile)}</small></div>
        <strong>VS</strong>
        <div><span>Player B</span><b>${escapeHtml(state.player2)}</b><small>${p2Profile.source === 'unavailable' ? 'Profile only' : surfaceEloText(playerRecord(state.player2), p2Profile)}</small></div>
      </div>
      <div class="inputs">
        <label>Player 1<input id="p1" autocomplete="off" spellcheck="false" value="${p1Value}"></label>
        <label>Player 2<input id="p2" autocomplete="off" spellcheck="false" value="${p2Value}"></label>
        <label>Surface<select id="slam">${['Hard Court', 'Clay Court', 'Grass Court'].map(surfaceName => `<option ${surfaceName === state.slam ? 'selected' : ''}>${surfaceName}</option>`).join('')}</select></label>
        <button class="predict" id="predict">Predict</button>
      </div>

      <div class="finder">
        <div class="tabs">
          <button data-slot="player1" class="${state.activeSlot === 'player1' ? 'active' : ''}">Fill Player 1</button>
          <button data-slot="player2" class="${state.activeSlot === 'player2' ? 'active' : ''}">Fill Player 2</button>
        </div>
        <label>Find player<input id="finder" autocomplete="off" value="${escapeHtml(state.search)}" placeholder="Search current players…"></label>
        <div class="results">${playerResultsHtml()}</div>
      </div>

      ${backendPredictionMarkup()}
    </section>

    ${backendMetricCards()}

    `;
}

function actionButton(label, page) {
  return `<button class="primary-action" data-page="${page}">${label}</button>`;
}

function todayPage() {
  return `${pageHeader('TODAY', 'Your tennis command centre.', 'See training, weather prep, match work and next actions without hunting through the app.')}
    <section class="dashboard">
      <article class="card session-card">
        <span class="eyebrow">NEXT SESSION</span>
        <h2>45-minute court session</h2>
        <ol class="clean-list">
          <li><b>8 min</b><span>Dynamic warm-up, split steps and shoulder prep.</span></li>
          <li><b>22 min</b><span>Cross-court consistency: 12 clean balls before changing direction.</span></li>
          <li><b>15 min</b><span>Serve + first-ball pattern: wide serve, recover, attack open court.</span></li>
        </ol>
        ${actionButton('Start training', 'train/plan')}
      </article>
      <article class="card weather-card">
        <span class="eyebrow">MATCH CONDITIONS</span>
        <h2>31° · warm</h2>
        <p>Add a drink break every 15–20 minutes. In heat, keep the first ten minutes controlled and avoid full-power serving too early.</p>
      </article>
    </section>`;
}

const LEARN_COACHING = {
  contact: {
    nav: 'Contact', kicker: 'FOREHAND SPACING', title: 'Contact in front',
    situation: 'A rally ball is arriving to the forehand side.',
    notice: 'Contact position changes spacing and the time available to recover.',
    best: 'Meet the ball slightly in front of the lead hip.',
    cue: 'Turn before the bounce. Create space, strike, then recover.',
    options: [['early', 'Early'], ['ideal', 'Ideal'], ['late', 'Late']],
    feedback: {
      early: ['Reaching too soon', 'Contact moves beyond the stable hitting window; control becomes harder.'],
      ideal: ['Balanced spacing', 'Contact sits slightly in front of the lead hip, leaving a clean recovery step.'],
      late: ['Recovery becomes rushed', 'Space collapses beside the body and the next movement starts late.']
    }
  },
  net: {
    nav: 'Net opponent', kicker: 'TACTICAL GEOMETRY', title: 'Use the space around the volleyer',
    situation: 'The opponent has closed near the net while you are behind the baseline.',
    notice: 'Their position protects the middle but leaves space low, wide, and overhead.',
    best: 'Pass low cross-court when balanced; lift the lob when they close tightly.',
    cue: 'Choose geometry before power.',
    options: [['pass', 'Pass'], ['lob', 'Lob'], ['drive', 'Drive through']],
    feedback: {
      pass: ['Low passing lane', 'Cross-court shape makes the first volley lower and farther from the centre.'],
      lob: ['Space behind', 'Height uses the open court behind an opponent positioned tight to the net.'],
      drive: ['Lower percentage', 'The straight lane runs through the opponent’s strongest coverage zone.']
    }
  },
  recovery: {
    nav: 'Lob recovery', kicker: 'MOVEMENT MECHANICS', title: 'Turn, cross over, recover',
    situation: 'A lob travels over the hitting shoulder and forces movement toward the baseline.',
    notice: 'Body orientation determines balance, speed, and how much court remains covered.',
    best: 'Open the hips and use crossover steps before resetting high.',
    cue: 'Turn first. Run to the ball. Rebuild balance before the next shot.',
    options: [['turn', 'Turn + crossover'], ['backpedal', 'Backpedal']],
    feedback: {
      turn: ['Balanced court coverage', 'The hips open to the recovery direction and crossover steps cover ground efficiently.'],
      backpedal: ['Unstable recovery', 'The feet travel behind the body, reducing speed and making balance harder to keep.']
    }
  }
};

function coachingCourtLines() {
  return '<i class="coach-line outer"></i><i class="coach-line net"></i><i class="coach-line service-a"></i><i class="coach-line service-b"></i><i class="coach-line centre"></i>';
}

function learnCanvasMarkup(lessonId, choice, step) {
  const lines = coachingCourtLines();
  if (lessonId === 'contact') {
    return `<div class="interactive-court contact-canvas choice-${choice} step-${step}" role="img" aria-label="Forehand contact timing demonstration: ${choice}">
      ${lines}<span class="measure measure-spacing">BODY–BALL SPACING</span><span class="coach-player hitter"><i></i></span>
      <span class="incoming-track"><i class="coach-ball"></i></span><span class="contact-window"></span><span class="contact-point"></span>
      <span class="swing-arc"></span><span class="recovery-vector"></span><small class="canvas-caption contact-caption">CONTACT</small><small class="canvas-caption recovery-caption">RECOVERY</small>
    </div>`;
  }
  if (lessonId === 'net') {
    return `<div class="interactive-court net-canvas choice-${choice} step-${step}" role="img" aria-label="Net opponent tactical choice demonstration: ${choice}">
      ${lines}<span class="coverage-zone"></span><span class="lob-space"></span><span class="coach-player baseline-player"><i></i></span><span class="coach-player net-player"><i></i></span>
      <span class="coach-shot-path pass-line"></span><span class="coach-shot-path lob-line"><i class="coach-ball"></i></span><span class="coach-shot-path drive-line"></span>
      <small class="canvas-caption lane-caption">PASSING LANE</small><small class="canvas-caption space-caption">OPEN SPACE</small><small class="canvas-caption coverage-caption">NET COVERAGE</small>
    </div>`;
  }
  return `<div class="interactive-court recovery-canvas choice-${choice} step-${step}" role="img" aria-label="Lob recovery movement demonstration: ${choice}">
    ${lines}<span class="recovery-start"></span><span class="coach-player recovery-player"><i></i></span><span class="lob-track"><i class="coach-ball"></i></span>
    <span class="movement-line crossover-line"></span><span class="movement-line backpedal-line"></span><span class="balance-zone"></span>
    <small class="canvas-caption turn-caption">TURN + CROSSOVER</small><small class="canvas-caption back-caption">BACKPEDAL</small><small class="canvas-caption balance-caption">BALANCED RESET</small>
  </div>`;
}

function curriculumFor(level = state.learnLevel) {
  return LEARN_CURRICULUM[level] || LEARN_CURRICULUM.Beginner;
}

function findLearnLesson(id, level = state.learnLevel) {
  for (const category of curriculumFor(level)) {
    const lesson = category.lessons.find(item => item.id === id);
    if (lesson) return { lesson, category };
  }
  return null;
}

function learnHistorySnapshot() {
  return { level: state.learnLevel, category: state.learnCategory, lesson: state.learnOpenLesson };
}

function updateLearnView(update) {
  if (!history.state?.courtiqLearn) history.replaceState({ ...(history.state || {}), courtiqLearn: learnHistorySnapshot() }, '');
  Object.assign(state, update);
  localStorage.cqLearnLevel = state.learnLevel;
  history.pushState({ ...(history.state || {}), courtiqLearn: learnHistorySnapshot() }, '');
  render();
}

function learnDiagram(lesson) {
  if (!lesson.visual || !LEARN_COACHING[lesson.visual]) return '';
  const coaching = LEARN_COACHING[lesson.visual];
  const choice = coaching.feedback[state.learnChoice[lesson.visual]] ? state.learnChoice[lesson.visual] : coaching.options[0][0];
  state.learnLesson = lesson.visual;
  const step = Math.max(1, Math.min(3, Number(state.learnStep) || 1));
  return `<section class="lesson-see-it" aria-labelledby="see-it-title">
    <div class="lesson-section-head"><span>SEE IT</span><h3 id="see-it-title">${coaching.title}</h3></div>
    <div class="lesson-visual-grid">
      <div class="lesson-visual-stage">${learnCanvasMarkup(lesson.visual, choice, step)}</div>
      <div class="lesson-visual-controls">
        <div class="decision-control" role="group" aria-label="${coaching.nav} choices">
          ${coaching.options.map(([id, label]) => `<button type="button" data-learn-choice="${id}" class="${id === choice ? 'active' : ''}" aria-pressed="${id === choice}">${label}</button>`).join('')}
        </div>
        <div class="choice-feedback" aria-live="polite"><span>${coaching.feedback[choice][0]}</span><p>${coaching.feedback[choice][1]}</p></div>
        <div class="step-control" aria-label="Demonstration step">
          ${[['1', 'Setup'], ['2', 'Decision'], ['3', 'Recovery']].map(([id, label]) => `<button type="button" data-learn-step="${id}" class="${Number(id) === step ? 'active' : ''}" aria-pressed="${Number(id) === step}"><span>${id}</span>${label}</button>`).join('')}
        </div>
      </div>
    </div>
  </section>`;
}

function learnLessonPage(found) {
  const { lesson, category } = found;
  const related = lesson.related.map(id => findLearnLesson(id)).filter(Boolean);
  const puzzleRelevant = lesson.visual === 'net' || /serve \+1|return|defen|approach|volley|matchup/i.test(`${lesson.title} ${category.title}`);
  return `<section class="learn-lesson-detail">
    <button type="button" class="lesson-back" data-learn-back>← ${state.learnLevel} curriculum</button>
    <header class="lesson-detail-head"><div><span class="eyebrow">${category.title}</span><h2>${lesson.title}</h2></div><span class="lesson-level-chip">${state.learnLevel}</span></header>
    <div class="lesson-concept"><span>CONCEPT</span><p>${lesson.concept}</p><strong>${lesson.why}</strong></div>
    ${learnDiagram(lesson)}
    <div class="lesson-guidance-grid">
      <section><span>KEY CUES</span><ul>${lesson.cues.map(cue => `<li>${cue}</li>`).join('')}</ul></section>
      <section><span>COMMON MISTAKE</span><p>${lesson.mistake}</p></section>
      <section class="lesson-drill"><span>TRY IT</span><p>${lesson.drill}</p></section>
    </div>
    ${(related.length || puzzleRelevant) ? `<footer class="lesson-related"><span>RELATED</span><div>${related.map(({ lesson: item }) => `<button type="button" data-learn-related="${item.id}">${item.title}</button>`).join('')}${puzzleRelevant ? '<button type="button" data-page="train/puzzles">Practice in Puzzle Court ↗</button>' : ''}</div></footer>` : ''}
  </section>`;
}

function learnPage() {
  const levels = ['Beginner', 'Intermediate', 'Advanced'];
  const curriculum = curriculumFor();
  if (!curriculum.some(category => category.id === state.learnCategory)) state.learnCategory = curriculum[0].id;
  const open = state.learnOpenLesson ? findLearnLesson(state.learnOpenLesson) : null;
  const activeCategory = curriculum.find(category => category.id === state.learnCategory) || curriculum[0];
  return `${pageHeader('LEARN', 'Build patterns that hold up in a match.', 'A levelled tennis curriculum for technique, movement, tactics and pressure decisions.')}
    <section class="learn-shell">
      <div class="learn-level-bar"><span>CURRICULUM LEVEL</span><div role="group" aria-label="Curriculum level">${levels.map(level => `<button type="button" data-learn-level="${level}" class="${level === state.learnLevel ? 'active' : ''}" aria-pressed="${level === state.learnLevel}">${level}</button>`).join('')}</div></div>
      ${open ? learnLessonPage(open) : `<div class="curriculum-layout">
        <nav class="curriculum-categories" aria-label="${state.learnLevel} lesson categories">
          <header><span>${state.learnLevel.toUpperCase()}</span><strong>${curriculum.reduce((total, category) => total + category.lessons.length, 0)} concepts</strong></header>
          ${curriculum.map((category, index) => `<button type="button" data-learn-category="${category.id}" class="${category.id === activeCategory.id ? 'active' : ''}" aria-current="${category.id === activeCategory.id ? 'true' : 'false'}"><span>${String(index + 1).padStart(2, '0')}</span><strong>${category.title}</strong><small>${category.lessons.length} lessons</small></button>`).join('')}
        </nav>
        <section class="curriculum-lessons">
          <header><span class="eyebrow">${state.learnLevel} · ${String(curriculum.indexOf(activeCategory) + 1).padStart(2, '0')}</span><h2>${activeCategory.title}</h2><p>Select a lesson for the concept, key cues, common error and a court-ready drill.</p></header>
          <div class="lesson-list">${activeCategory.lessons.map((lesson, index) => `<button type="button" data-learn-open="${lesson.id}"><span>${String(index + 1).padStart(2, '0')}</span><div><strong>${lesson.title}</strong><small>${lesson.concept}</small></div><i aria-hidden="true">→</i></button>`).join('')}</div>
        </section>
      </div>`}
    </section>
    ${!open ? `<section class="learn-puzzle-link"><div><span class="eyebrow">DECISION TRAINING</span><h2>Apply tactics in Puzzle Court</h2><p>Use court-position scenarios to practise shot selection after learning the pattern.</p></div>${actionButton('Open Puzzle Court', 'train/puzzles')}</section>` : ''}`;
}

function currentPuzzle() {
  const puzzle = generatePuzzleScenario(state.puzzleSeed, {
    category: state.puzzleCategory,
    difficulty: state.puzzleDifficulty,
    surface: state.puzzleSurface
  });
  const step = Math.min(state.puzzleStep, puzzle.steps.length - 1);
  return { puzzle, step, item: puzzle.steps[step] };
}

function nextPuzzleId() {
  return nextPuzzleSeed();
}

function puzzleTargetForOption(option, index) {
  const text = normalizeKey(option);
  if (text.includes('lob')) return { x: 50, y: 9, kind: 'lob' };
  if (text.includes('line') || text.includes('behind')) return { x: index % 2 ? 78 : 22, y: 17, kind: 'line' };
  if (text.includes('cross')) return { x: index % 2 ? 24 : 76, y: 23, kind: 'cross' };
  if (text.includes('body') || text.includes('middle')) return { x: 50, y: 27, kind: 'middle' };
  if (text.includes('short') || text.includes('drop')) return { x: index % 2 ? 38 : 62, y: 39, kind: 'short' };
  if (text.includes('wide')) return { x: index % 2 ? 18 : 82, y: 21, kind: 'wide' };
  return { x: 34 + (index % 3) * 16, y: 25 + (index % 2) * 8, kind: 'neutral' };
}

function puzzleGeometry(puzzle, options) {
  const scenario = puzzle.scenario || {};
  const playerZones = {
    'wide outside doubles alley': [16, 91], 'behind baseline': [50, 91], 'baseline center': [50, 86],
    'inside baseline': [50, 74], 'service line': [50, 63]
  };
  const opponentZones = {
    'wide forehand corner': [78, 9], 'wide backhand corner': [22, 9], 'behind baseline': [50, 9],
    'baseline center': [50, 14], 'inside baseline': [50, 26], 'service line': [50, 37], 'tight to net': [50, 45]
  };
  const player = playerZones[scenario.playerZone] || [50, 88];
  const opponent = opponentZones[scenario.opponentZone] || [50, 12];
  const ball = [
    scenario.side === 'forehand' ? Math.min(88, player[0] + 14) : scenario.side === 'backhand' ? Math.max(12, player[0] - 14) : player[0],
    scenario.depth === 'short' ? 62 : scenario.depth === 'deep' ? 82 : scenario.depth === 'low at feet' ? 76 : 69
  ];
  const targets = options.map(puzzleTargetForOption);
  return { player, opponent, ball, targets, recovery: [50, 84] };
}

function rallyCourtMarkup(item, step) {
  const { puzzle } = currentPuzzle();
  const scenario = puzzle.scenario || {};
  const options = item[3] || [];
  const bestIndex = Number(item[4] || 0);
  const geometry = puzzleGeometry(puzzle, options);
  const [px, py] = geometry.player;
  const [ox, oy] = geometry.opponent;
  const [bx, by] = geometry.ball;
  const preferred = geometry.targets[bestIndex] || geometry.targets[0] || { x: 50, y: 25 };
  const answered = Boolean(state.puzzleFeedback);
  const incomingPath = `M ${ox} ${oy + 3} Q ${(ox + bx) / 2 + 5} ${(oy + by) / 2} ${bx} ${by}`;
  const preferredPath = `M ${bx} ${by} Q ${(bx + preferred.x) / 2 - 7} ${(by + preferred.y) / 2 - 8} ${preferred.x} ${preferred.y}`;
  const recoveryPath = `M ${px} ${py} Q ${(px + geometry.recovery[0]) / 2} ${py - 4} ${geometry.recovery[0]} ${geometry.recovery[1]}`;
  const surfaceKey = normalizeKey(scenario.surface || 'hard');
  const surfaceClass = surfaceKey.includes('clay') ? 'clay' : surfaceKey.includes('grass') ? 'grass' : 'hard';
  return `<section class="tactical-board-pro surface-${surfaceClass}" data-puzzle-geometry="${px},${py};${ox},${oy};${bx},${by}">
    <header class="tactical-context"><b>${escapeHtml(item[0])}</b><span>${escapeHtml(scenario.surface || '')}</span><span>${escapeHtml(scenario.category || '')}</span><span>${escapeHtml(scenario.balance || '')}</span></header>
    <div class="tactical-state"><span><i class="legend-you"></i>You: ${escapeHtml(scenario.playerZone || '')} / ${escapeHtml(scenario.balance || '')}</span><span><i class="legend-opponent"></i>Opponent: ${escapeHtml(scenario.opponentZone || '')}</span></div>
    <svg class="court-tactical-svg" viewBox="0 0 100 100" role="img" aria-label="Top-down tennis tactical board">
      <defs>
        <marker id="incoming-arrow" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto"><path d="M0,0 L4,2 L0,4 Z"></path></marker>
        <marker id="preferred-arrow" markerWidth="4" markerHeight="4" refX="3" refY="2" orient="auto"><path d="M0,0 L4,2 L0,4 Z"></path></marker>
      </defs>
      <rect class="court-outer" x="10" y="3" width="80" height="94"></rect>
      <line class="court-line" x1="10" y1="50" x2="90" y2="50"></line>
      <line class="court-line service" x1="18" y1="32" x2="82" y2="32"></line><line class="court-line service" x1="18" y1="68" x2="82" y2="68"></line>
      <line class="court-line singles" x1="18" y1="3" x2="18" y2="97"></line><line class="court-line singles" x1="82" y1="3" x2="82" y2="97"></line>
      <line class="court-line center" x1="50" y1="32" x2="50" y2="68"></line>
      <line class="court-line center-mark" x1="50" y1="3" x2="50" y2="5"></line><line class="court-line center-mark" x1="50" y1="95" x2="50" y2="97"></line>
      <line class="court-net" x1="7" y1="50" x2="93" y2="50"></line>
      ${geometry.targets.map((target, index) => `<g class="decision-target" data-target-index="${index}"><ellipse cx="${target.x}" cy="${target.y}" rx="7" ry="4"></ellipse><text x="${target.x}" y="${target.y + 1.2}" text-anchor="middle">${String.fromCharCode(65 + index)}</text></g>`).join('')}
      <path class="incoming-trajectory" d="${incomingPath}" marker-end="url(#incoming-arrow)"></path>
      ${answered ? `<path class="preferred-trajectory" d="${preferredPath}" marker-end="url(#preferred-arrow)"></path><path class="recovery-trajectory" d="${recoveryPath}"></path>` : ''}
      <g class="athlete-marker opponent-marker" transform="translate(${ox} ${oy})"><circle r="3.2"></circle><path d="M-4 1 L0 -4 L4 1"></path><text y="-6" text-anchor="middle">OPP</text></g>
      <g class="athlete-marker user-marker ${escapeHtml(scenario.balance || '')}" transform="translate(${px} ${py})"><circle r="3.2"></circle><path d="M-4 -1 L0 4 L4 -1"></path><text y="8" text-anchor="middle">YOU</text></g>
      <g class="precise-ball" transform="translate(${bx} ${by})"><circle r="1.45"></circle><path d="M-1.1 -.5 Q0 0 1.1 .5"></path></g>
    </svg>
    ${answered ? `<footer class="tactical-resolution"><span><b>Preferred</b>${escapeHtml(options[bestIndex] || '')}</span><span><b>Alternative</b>${escapeHtml(state.puzzleLastChoice || '')}</span></footer>` : ''}
  </section>`;
}

function puzzlesPage() {
  const { puzzle, step, item } = currentPuzzle();
  const [score, situation, courtText, options, bestIndex, explanation] = item;
  const complete = Boolean(state.puzzleFeedback);
  const stats = state.puzzleStats || { attempted: 0, correct: 0, categories: {} };
  const categoryOptions = ['Random', ...PUZZLE_CATEGORIES].map(value => `<option value="${escapeHtml(value)}" ${state.puzzleCategory === value ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
  const difficultyOptions = ['Any difficulty', ...PUZZLE_DIFFICULTIES].map(value => `<option value="${escapeHtml(value)}" ${state.puzzleDifficulty === value ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
  const surfaceOptions = ['Any surface', ...PUZZLE_SURFACES].map(value => `<option value="${escapeHtml(value)}" ${state.puzzleSurface === value ? 'selected' : ''}>${escapeHtml(value)}</option>`).join('');
  const activeCategory = puzzle.category || 'Pattern';
  const weakCategories = Object.entries(stats.categories || {})
    .filter(([, value]) => value.attempted >= 3)
    .sort((a, b) => (a[1].correct / a[1].attempted) - (b[1].correct / b[1].attempted))
    .slice(0, 3);
  return `${pageHeader('PUZZLE COURT', 'Train decisions under pressure.', 'Pick a training mode, read the court, choose a shot, then advance to the next tactical situation.')}
    <section class="puzzle-shell">
      <div class="puzzle-session-meta"><span>${escapeHtml(activeCategory)}</span><span>${escapeHtml(puzzle.difficulty || '')}</span><span>${escapeHtml(puzzle.surface || '')}</span></div>
      <article class="puzzle-training-panel">
        <div>
          <span class="eyebrow">TRAINING SETUP</span>
          <h2>Generate your next decision</h2>
          <p>Each scenario is sampled on demand from court position, pressure, surface, rally phase and opponent archetype.</p>
        </div>
        <label>Category<select id="puzzle-category">${categoryOptions}</select></label>
        <label>Difficulty<select id="puzzle-difficulty">${difficultyOptions}</select></label>
        <label>Surface<select id="puzzle-surface">${surfaceOptions}</select></label>
        <button id="start-puzzle-training" class="primary-action">Start Training</button>
      </article>
      <article class="puzzle-card">
        <div class="puzzle-copy">
          <span class="eyebrow">${escapeHtml(puzzle.opponent)}</span>
          <h2>${escapeHtml(puzzle.name)}</h2>
          <p><b>${escapeHtml(score)}</b> — ${escapeHtml(situation)}</p>
          <small>${escapeHtml(courtText)}</small>
          <div class="puzzle-tags">
            ${(puzzle.tags || [activeCategory]).map(tag => `<span>${escapeHtml(tag)}</span>`).join('')}
          </div>
        </div>
        ${rallyCourtMarkup(item, step)}
      </article>
      <article class="puzzle-actions">
        <span class="eyebrow">${complete ? 'POINT FINISHED' : 'CHOOSE YOUR NEXT MOVE'}</span>
        <div class="puzzle-options">
          ${options.map((option, index) => `<button data-puzzle-answer="${index}" data-target-index="${index}" class="${state.puzzleLastChoice === option ? 'selected' : ''}" ${complete ? 'disabled' : ''}>
            <em>${String.fromCharCode(65 + index)}</em><b>${escapeHtml(option)}</b><small>${index === bestIndex && state.puzzleFeedback ? 'Preferred pattern' : 'Tactical option'}</small>
          </button>`).join('')}
        </div>
        <div class="puzzle-feedback ${state.puzzleFeedback ? 'show' : ''}">
          ${state.puzzleFeedback || 'Pick the highest-percentage shot for this court position.'}
          <br><b>Coach note:</b> ${escapeHtml(explanation)}
        </div>
        <div class="puzzle-flow-actions">
          <button id="reset-puzzle" class="ghost-action">Reset current point</button>
          <button id="next-puzzle" class="primary-action">${complete ? 'Play another puzzle' : 'Next Scenario'}</button>
        </div>
      </article>
      <article class="puzzle-library puzzle-dashboard">
        <span class="eyebrow">TACTICAL NOTES</span>
        <h2>${stats.attempted < 5 ? 'More decisions are needed for a useful pattern note' : 'Lowest-confidence tactical areas'}</h2>
        <p>${stats.attempted} decisions reviewed. This history can inform Plan emphasis; it is not a score or achievement system.</p>
        <div>
          ${weakCategories.length
            ? weakCategories.map(([name, value]) => `<span><b>${escapeHtml(name)}</b><small>${value.correct} preferred choices across ${value.attempted} reviewed decisions</small></span>`).join('')
            : PUZZLE_CATEGORIES.slice(0, 7).map(name => `<span><b>${escapeHtml(name)}</b><small>Not enough reps yet</small></span>`).join('')}
        </div>
      </article>
    </section>`;
}

function analyzePage() {
  return `${pageHeader('ANALYZE', 'Pose-based movement analysis.', 'Upload one short tennis clip. CourtIQ reports only what its 2D landmark pass can genuinely measure.')}
    <section class="analyze-workbench">
      <article class="video-viewport" id="drop-zone">
        <div class="analysis-frame" aria-hidden="true"><i></i><i></i><i></i></div>
        <div id="video-empty-state" class="video-empty-state">
          <span class="upload-icon">↑</span><h2>Drop a tennis video here</h2><p>or choose a video</p>
          <input id="video-upload" class="native-video-upload" type="file" accept="video/*,.mp4,.mov,.m4v,.webm" aria-label="Choose Video">
          <small>MP4, MOV, M4V or WebM · maximum 80 MB</small>
        </div>
        <div id="video-preview-state" class="video-preview-state" hidden>
          <video id="selected-video-preview" controls playsinline preload="metadata"></video>
          <div class="selected-video-meta">
            <div><b id="selected-file-name">No video selected</b><span id="selected-video-details"></span></div>
            <div class="video-file-actions"><label class="ghost-action" for="video-upload">Replace</label><button type="button" id="remove-video" class="ghost-action">Remove</button></div>
          </div>
        </div>
      </article>
      <aside class="analysis-readiness">
        <span class="eyebrow">ANALYSIS READINESS</span><h2 id="readiness-title">Waiting for footage</h2>
        <div id="readiness-facts" class="readiness-facts"><p>Select a valid video to inspect browser-detectable metadata.</p></div>
        <small id="upload-error" class="upload-error" aria-live="polite"></small>
        <button id="analyze-btn" class="primary-action" type="button" disabled>Analyze Video</button>
        <div class="recording-guidance"><b>For best results</b><span>8–20 second clip</span><span>Stable camera · full body visible</span><span>Good lighting · athlete large in frame</span></div>
      </aside>
    </section>
    <section class="analysis-stage-flow" aria-label="Analysis workflow">
      ${['Reading footage', 'Detecting player', 'Tracking landmarks', 'Identifying movement', 'Measuring available mechanics', 'Building report'].map((step, index) => `<span><b>${String(index + 1).padStart(2, '0')}</b>${escapeHtml(step)}</span>`).join('')}
    </section>
    <section id="analysis-report" class="analysis-report" aria-live="polite"></section>`;
}

function trainPage() {
  const store = trainStore();
  const activePlan = store.activePlan;
  const sessions = activePlan?.sessions || [];
  const recommendedSession = sessions.find(item => item.status !== 'completed') || sessions[0];
  const selectedSession = sessions.find(item => item.id === activePlan?.selectedSessionId) || recommendedSession;
  const sessionGroups = sessions.reduce((groups, session) => {
    groups[session.week] = groups[session.week] || [];
    groups[session.week].push(session);
    return groups;
  }, {});
  return `${pageHeader('PLAN', 'Build training around your tennis.', 'Choose the practical constraints. CourtIQ creates progressive sessions with exact blocks and sensible durations.')}
    <section class="train-plan-shell">
      <article class="plan-builder">
        <div><span class="eyebrow">CREATE A PLAN</span><h2>Training parameters</h2></div>
        <div class="plan-fields">
          <label>Primary goal<select id="plan-goal">${TRAINING_GOALS.map(goal => `<option>${escapeHtml(goal)}</option>`).join('')}</select></label>
          <label>Level<select id="plan-level">${PLAN_LEVELS.map(level => `<option>${level}</option>`).join('')}</select></label>
          <label>Days per week<select id="plan-days">${[1,2,3,4,5,6].map(day => `<option ${day === 3 ? 'selected' : ''}>${day}</option>`).join('')}</select></label>
          <label>Session duration<select id="plan-duration">${[30,45,60,75,90].map(value => `<option ${value === 60 ? 'selected' : ''} value="${value}">${value} minutes</option>`).join('')}</select></label>
          <label>Program length<select id="plan-weeks">${[[0,'Single session'],[1,'1 week'],[2,'2 weeks'],[4,'4 weeks'],[6,'6 weeks'],[8,'8 weeks']].map(([value,label]) => `<option value="${value}">${label}</option>`).join('')}</select></label>
        </div>
        <button id="generate-plan" class="primary-action">Generate Plan</button>
      </article>
      ${activePlan ? `<article class="active-plan-summary">
        <span class="eyebrow">ACTIVE PLAN</span><h2>${escapeHtml(activePlan.goal)} · ${activePlan.weeks === 0 ? 'single session' : `${activePlan.weeks} weeks`}</h2>
        <p>${activePlan.days} days/week · ${activePlan.duration} minutes · ${escapeHtml(activePlan.level)} · ${sessions.length} scheduled sessions</p>
        <button id="replace-plan" class="ghost-action">Regenerate / replace</button>
      </article>` : '<article class="active-plan-summary"><span class="eyebrow">ACTIVE PLAN</span><h2>No active plan</h2><p>Generate one from the fields above.</p></article>'}
      ${selectedSession ? `<article class="plan-board">
        <div class="section-head session-header">
          <div><span class="eyebrow">${selectedSession.id === recommendedSession?.id ? "TODAY'S SESSION" : 'SELECTED SESSION'}</span><h2>${escapeHtml(selectedSession.phase)}</h2><p>Week ${selectedSession.week} · Day ${selectedSession.day} · ${selectedSession.duration} min</p></div>
          <button class="ghost-action" data-session-complete="${escapeHtml(selectedSession.id)}">${selectedSession.status === 'completed' ? 'Undo completion' : 'Mark session complete'}</button>
        </div>
        <div class="plan-list">
          ${selectedSession.blocks.map((item, index) => `<div class="plan-row"><span>${String(index + 1).padStart(2, '0')}</span><div><em>${escapeHtml(item.type)}</em><b>${escapeHtml(item.title)}</b><p>${escapeHtml(item.drill)}</p><small><strong>Target</strong>${escapeHtml(item.target)}</small></div><time>${item.minutes} min</time></div>`).join('')}
        </div>
      </article>` : ''}
      ${sessions.length ? `<article class="upcoming-sessions"><span class="eyebrow">PLAN SESSIONS</span><div class="upcoming-list">${Object.entries(sessionGroups).map(([week, weekSessions]) => `<section class="plan-week"><h3>WEEK ${week}</h3>${weekSessions.map(item => {
        const status = item.status === 'completed' ? 'Completed' : item.id === recommendedSession?.id ? 'Current' : 'Upcoming';
        return `<button type="button" class="upcoming-row ${item.id === selectedSession?.id ? 'selected' : ''}" data-plan-session="${escapeHtml(item.id)}" ${item.id === selectedSession?.id ? 'aria-current="true"' : ''}><div><b>Day ${item.day}</b><span>${escapeHtml(item.phase)}</span><small>${status}</small></div><time>${item.duration} min</time></button>`;
      }).join('')}</section>`).join('')}</div></article>` : ''}
    </section>`;
}

function competePage() {
  const groups = groupedUpcomingPredictions();
  return `${pageHeader('PREDICTIONS', 'Upcoming match forecast feed.', 'Verified scheduled matches across tournaments, grouped chronologically without requiring tournament selection.')}
    ${tourSelectorMarkup()}
    <section class="prediction-feed">
      ${groups.length ? groups.map(([tournament, matches]) => {
        const first = matches[0];
        return `<section class="prediction-tournament">
          <header><h2>${escapeHtml(tournament).toUpperCase()}</h2><p>${escapeHtml([first.tour, first.level, first.surface, first.location].filter(Boolean).join(' · '))}</p></header>
          ${matches.map(match => {
            const a = Math.round(Number(match.player_a_probability) * 1000) / 10;
            const b = Math.round((100 - a) * 10) / 10;
            return `<div class="prediction-line" style="--p:${a}%"><b>${escapeHtml(match.player_a)}</b><span>${a}%</span><i><em></em></i><span>${b}%</span><b>${escapeHtml(match.player_b)}</b><small>${escapeHtml([match.round, match.match_at].filter(Boolean).join(' · '))}</small></div>`;
          }).join('')}
        </section>`;
      }).join('') : `<div class="verified-feed-empty"><h2>No verified upcoming ${escapeHtml(state.selectedTour)} fixtures loaded</h2><p>CourtIQ will not invent future matches. Add verified schedule records to the prediction feed source to display forecasts here.</p></div>`}
    </section>`;
}

function gearPage() {
  const categories = ['All', 'Racket', 'Shoes', 'Ball', 'String', 'Bag', 'Grip', 'Dampener', 'Accessory'];
  const categoryLabels = { Racket: 'Rackets', Ball: 'Balls', String: 'Strings', Shoes: 'Shoes', Bag: 'Bags', Grip: 'Grips', Dampener: 'Dampeners', Accessory: 'Accessories', All: 'All' };
  if (state.gearMode === 'All') state.gearMode = 'Both';
  if (!['Both', 'Online', 'Nearby Stores'].includes(state.gearMode)) state.gearMode = 'Both';
  const brands = ['All brands', ...Array.from(new Set(REAL_GEAR_ITEMS.map(item => item.brand).filter(Boolean))).sort()];
  if (!categories.includes(state.gearType)) state.gearType = 'All';
  if (!brands.includes(state.gearBrand)) state.gearBrand = 'All brands';
  const personalized = sortedGearItems(REAL_GEAR_ITEMS);
  const topPicks = personalized.slice(0, 8);
  const recentInterest = gearInterest();
  const watchedBrands = Object.entries(recentInterest.brands || {}).sort((a, b) => b[1] - a[1]).map(([brand]) => brand).slice(0, 4);
  const continueItems = watchedBrands.length
    ? personalized.filter(item => watchedBrands.includes(item.brand)).slice(0, 8)
    : FEATURED_REAL_GEAR_ITEMS.slice(0, 8);
  const brandSections = brands
    .filter(brand => brand !== 'All brands')
    .map(brand => ({
      brand,
      items: personalized.filter(item => item.brand === brand).slice(0, 8),
      count: REAL_GEAR_ITEMS.filter(item => item.brand === brand).length
    }))
    .filter(section => section.items.length);
  const meta = GEAR_INDEX.metadata || {};
  const totalProducts = Number(meta.total_products || REAL_GEAR_ITEMS.length);
  const imageCount = Number(meta.products_with_real_images || 0);
  const sourceCount = Array.isArray(meta.source_files) ? meta.source_files.length : 0;

  return `<section class="gear-hero">
      <div>
        <span class="eyebrow">GEAR</span>
        <h1>Find the right setup.</h1>
        <p>Search a refreshable product index by brand, category, surface and playing style. Results adapt to the filters you actually use.</p>
      </div>
    </section>
    <section class="gear-shell">
      <article class="gear-index-status">
        <div><span class="eyebrow">PRODUCT INDEX</span><h2>${escapeHtml(totalProducts)} indexed items</h2></div>
        <p>${escapeHtml(sourceCount)} source file${sourceCount === 1 ? '' : 's'} loaded · ${escapeHtml(imageCount)} verified product images stored · old seed data is fallback only.</p>
      </article>
      <div class="gear-toolbar">
        <label>City / country<input id="city-input" value="${escapeHtml(state.gearLocation)}" autocomplete="off" placeholder="Ahmedabad, London, New York…"></label>
        <label>Search products
          <span class="input-with-clear">
            <input id="gear-search" value="${escapeHtml(state.gearQuery)}" placeholder="Pure Drive, Wilson Blade, clay shoes…" autocomplete="off">
            <button type="button" id="clear-gear-search" aria-label="Clear gear search">×</button>
          </span>
        </label>
        <label>Buying mode<select id="buying-mode">
          ${['Both', 'Online', 'Nearby Stores'].map(mode => `<option value="${escapeHtml(mode)}" ${state.gearMode === mode ? 'selected' : ''}>${escapeHtml(mode)}</option>`).join('')}
        </select></label>
      </div>
      <div class="gear-filters">
        ${categories.map(type => `<button type="button" class="gear-filter ${type === state.gearType ? 'active' : ''}" data-gear-type="${type}">${categoryLabels[type]}</button>`).join('')}
        <select id="brand-filter">${brands.map(brand => `<option value="${escapeHtml(brand)}" ${state.gearBrand === brand ? 'selected' : ''}>${escapeHtml(brand)}</option>`).join('')}</select>
        <button id="reset-gear-memory" type="button" class="ghost-action compact">Reset gear learning</button>
      </div>
      <article id="gear-search-results" class="gear-section search-results-section">
        <div class="brand-section-head">
          <div><span class="eyebrow">SEARCH RESULTS</span><h2>Browse the index</h2></div>
          <p>Exact, prefix, token and fuzzy matching. Images and current prices appear only when source-backed.</p>
        </div>
        <div class="gear-grid"></div>
        <button type="button" id="load-more-gear" class="ghost-action compact" hidden>Load more products</button>
      </article>
      <article class="gear-recommendations gear-section" data-brand-section="recommendations">
        <div class="brand-section-head">
          <div><span class="eyebrow">RECOMMENDED</span><h2>Best matches</h2></div>
        </div>
        <div class="gear-grid recommendation-grid">
          ${topPicks.map(item => gearCardMarkup(item, 'recommended-card', gearRecommendationReason(item))).join('')}
        </div>
      </article>
      <article class="gear-section" data-brand-section="continue">
        <div class="brand-section-head">
          <div><span class="eyebrow">RECENT ACTIVITY</span><h2>${watchedBrands.length ? watchedBrands.join(', ') : 'Popular gear'}</h2></div>
        </div>
        <div class="gear-grid">
          ${continueItems.map(item => gearCardMarkup(item, 'interest-card')).join('')}
        </div>
      </article>
      <div class="brand-catalog">
        ${brandSections.slice(0, 8).map(section => `<section class="gear-section brand-section" data-brand-section="${escapeHtml(section.brand)}">
          <div class="brand-section-head">
            <div><span class="eyebrow">BRAND PREVIEW</span><h2>${escapeHtml(section.brand)}</h2></div>
          </div>
          <div class="gear-grid">${section.items.map(item => gearCardMarkup(item)).join('')}</div>
        </section>`).join('')}
      </div>
      <article id="store-output" class="store-output">
        <span class="eyebrow">SHOPPING</span>
        <h2>Select a product</h2>
        <p>Choose a product. CourtIQ opens a real store/map search using your selected city and buying mode.</p>
      </article>
    </section>`;
}

function profilePage() {
  return `${pageHeader('PROFILE', 'Your private tennis profile.', 'Save preferences once so training, gear, hydration and analysis feel personal without repeating questions.')}
    <section class="feature-grid">
      <article class="feature-card">
        <span class="eyebrow">PLAYER</span>
        <h2>Competitive · right-handed</h2>
        <p>Favorite stroke, level, surface, city, height, weight and equipment preferences live here.</p>
      </article>
      <article class="feature-card dark">
        <span class="eyebrow">LOCAL RECORDS</span>
        <h2>Sessions and analysis reports</h2>
        <p>Completed training sessions and analyzed clips are saved locally on this device for the prototype.</p>
      </article>
      <article class="feature-card dark">
        <span class="eyebrow">DEVICE-LOCAL PROFILE</span>
        <h2>Private on this browser</h2>
        <p>This prototype has no authenticated account. Profile defaults remain in this browser until local data is cleared.</p>
      </article>
    </section>
    <section class="security-panel">
      <div class="section-head">
        <div><span class="eyebrow">SECURITY & PRIVACY</span><h2>Privacy controls</h2></div>
        <button class="danger-action" id="local-profile-reset" type="button">Reset local profile</button>
      </div>
      <div class="security-list">
        ${SECURITY_ITEMS.map(item => `<div class="security-row"><span>✓</span><b>${escapeHtml(item)}</b></div>`).join('')}
      </div>
    </section>`;
}

async function analyzeUploadedVideo() {
  const report = $('#analysis-report');
  const file = state.selectedVideo || $('#video-upload')?.files?.[0];
  if (!report) return;

  const validationError = validateVideoFile(file);
  if (validationError) {
    report.innerHTML = `<article class="analysis-empty"><h2>Video not ready</h2><p>${escapeHtml(validationError)}</p></article>`;
    const error = $('#upload-error');
    if (error) error.textContent = validationError;
    toast(validationError);
    return;
  }

  report.innerHTML = processingMarkup('Building your video report', [
    'Reading footage',
    'Detecting player visibility',
    'Tracking body landmarks',
    'Detecting strokes and movement',
    'Measuring mechanics',
    'Building analysis'
  ]);

  try {
    const form = new FormData();
    form.append('file', file);
    const response = await fetch(`${API_BASE}/api/video/analyze`, { method: 'POST', body: form });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(payload.detail || payload.error?.message || `Video API failed with ${response.status}`);
    renderPoseVideoReport(file, payload);
    toast('Video analysis ready.');
  } catch (error) {
    report.innerHTML = `<article class="analysis-empty">
      <h2>Video analysis could not run</h2>
      <p>${escapeHtml(error.message || `CourtIQ's analysis service is temporarily unavailable.`)}</p>
      <p>No report was fabricated. Please retry this clip shortly.</p>
    </article>`;
    toast('Video backend unavailable.');
  }
}

function renderPoseVideoReport(file, payload) {
  // Measurement implementation: OpenCV + MediaPipe body landmarks. Detailed
  // technical disclosure belongs in documentation rather than the primary UI.
  const report = $('#analysis-report');
  if (!report) return;
  const analysis = payload.analysis || {};
  const metrics = analysis.metrics || {};
  const detection = analysis.content_detection || {};
  const record = persistAnalysisRecord(file, payload);
  const entries = Object.entries(metrics);
  const topConfidence = Math.max(...entries.map(([, value]) => Number(value?.confidence || 0)), 0);
  const grouped = entries.reduce((groups, [name, metric]) => {
    const bucket = metricBucket(name);
    groups[bucket] = groups[bucket] || [];
    groups[bucket].push([name, metric]);
    return groups;
  }, {});
  const recommendations = record?.recommendations || recommendationsFromMetrics(metrics);
  const videoUrl = URL.createObjectURL(file);
  const timeline = (analysis.timestamps || []).slice(0, 6);
  const timelineMarkup = timeline.map((point, index) => `<button data-video-time="${Number(point.time || 0)}" style="--x:${Math.min(92, 8 + index * 16)}%">
        <b>${Number(point.time || 0).toFixed(1)}s</b><span>${escapeHtml(metricLabel(Object.keys(point).find(key => key !== 'time') || 'sample'))}</span>
      </button>`).join('');
  const metricRows = Object.entries(grouped).map(([bucket, rows]) => `<section class="metric-group">
    <h3>${escapeHtml(bucket)}</h3>
    ${rows.map(([name, value]) => `<div class="metric-row">
      <span>${escapeHtml(metricLabel(name))}</span>
      <b>${escapeHtml(value.mean ?? '—')}°</b>
      <small>${escapeHtml(value.min ?? '—')}–${escapeHtml(value.max ?? '—')}° · ${escapeHtml(qualityLabel(value.confidence))}</small>
    </div>`).join('')}
  </section>`).join('');

  if (analysis.status !== 'ok') {
    report.innerHTML = `<article class="analysis-output">
      <div class="report-head">
        <div><span class="eyebrow">VIDEO REPORT</span><h2>Insufficient confidence</h2><p>${escapeHtml(file.name)}</p></div>
        <b class="quality-score">${escapeHtml(String(analysis.status || 'not ready').replaceAll('_', ' '))}</b>
      </div>
      ${videoDetectionCardsMarkup(detection)}
      <div class="next-drill caution">
        <b>What happened</b>
        <p>${escapeHtml(analysis.reason || 'The uploaded clip did not produce enough reliable pose landmarks.')}</p>
      </div>
      <div class="next-drill">
        <b>Record again</b>
        <p>Use a clear rear 45° or side angle, keep the full body visible, and upload an 8–12 second clip.</p>
      </div>
      ${videoLimitationsMarkup(detection)}
    </article>`;
    return;
  }

  report.innerHTML = `<article class="analysis-output">
    <div class="report-head">
      <div>
        <span class="eyebrow">VIDEO REPORT</span>
        <h2>Automatic video report</h2>
        <p>${escapeHtml(file.name)}</p>
      </div>
      <b class="quality-score">Tracking quality: ${escapeHtml(qualityLabel(topConfidence))}</b>
    </div>
    <div class="video-workspace">
      <div class="video-viewer"><video id="analysis-video" controls preload="metadata" src="${videoUrl}"></video></div>
      <div class="analysis-summary">
        <span class="eyebrow">CLIP METADATA</span>
        <h3>${analysis.frames_processed} frames${detection.duration_seconds ? ` · ${escapeHtml(detection.duration_seconds)}s` : ''}${detection.frame_size?.width && detection.frame_size?.height ? ` · ${escapeHtml(detection.frame_size.width)}×${escapeHtml(detection.frame_size.height)}` : ''}</h3>
        <p>Pose landmarks detected · ${(file.size / 1024 / 1024).toFixed(1)} MB</p>
      </div>
    </div>
    ${videoDetectionCardsMarkup(detection)}
    ${timelineMarkup ? `<div class="timeline-rail" aria-label="Clickable measured moments"><i></i>${timelineMarkup}</div>` : ''}
    <div class="metric-board">
      ${metricRows || '<section class="metric-group"><h3>No stable metrics</h3><p>Try a clearer full-body clip.</p></section>'}
    </div>
    <div class="coach-recommendations">
      <div class="section-head recommendation-heading">
        <div><span class="eyebrow">WHAT TO IMPROVE NEXT</span><p>Priority coaching cues from this analysis</p></div>
        <button id="add-analysis-plan" class="primary-action">Add to training plan</button>
      </div>
      <div class="recommendation-list">
      ${recommendations.map((item, index) => `<section class="recommendation-row">
        <span class="recommendation-index">${String(index + 1).padStart(2, '0')}</span>
        <div class="recommendation-content">
          <h3>${escapeHtml(item.title)}</h3>
          <div class="recommendation-details">
            <p><b>Observed</b><span>${escapeHtml(item.saw)}</span></p>
            <p><b>Why</b><span>${escapeHtml(item.why)}</span></p>
            <p><b>Drill</b><span>${escapeHtml(item.drill)}</span></p>
            <p><b>Target</b><span>${escapeHtml(item.target)}</span></p>
          </div>
        </div>
      </section>`).join('')}
      </div>
    </div>
    ${videoLimitationsMarkup(detection)}
  </article>`;
  bindAnalysisReportControls(report);
}

function bindAnalysisReportControls(root = document) {
  $$('[data-video-time]', root).forEach(button => {
    button.onclick = () => {
      const video = $('#analysis-video', root) || $('#analysis-video');
      if (video) {
        video.currentTime = Number(button.dataset.videoTime || 0);
        video.play?.().catch(() => undefined);
      }
    };
  });
  $('#add-analysis-plan', root)?.addEventListener('click', () => {
    const added = addAnalysisToPlan();
    toast(added ? 'Added to training plan.' : 'Analyze a clip first.');
  });
}

function updateGearCards() {
  const rawQuery = $('#gear-search')?.value?.trim() || state.gearQuery || '';
  const type = $('.gear-filter.active')?.dataset.gearType || state.gearType || 'All';
  const brand = $('#brand-filter')?.value || state.gearBrand || 'All brands';
  const results = $('#gear-search-results');
  const resultsGrid = $('#gear-search-results .gear-grid');
  const loadMore = $('#load-more-gear');
  state.gearQuery = rawQuery;
  state.gearType = type;
  state.gearBrand = brand;
  state.gearLocation = $('#city-input')?.value?.trim() || state.gearLocation || '';
  state.gearMode = $('#buying-mode')?.value || state.gearMode || 'Both';
  saveState();

  if (rawQuery.length > 1) rememberGearInterest(null, rawQuery);

  if (results && resultsGrid) {
    const matches = filterGearIndexItems({ query: rawQuery, type, brand });
    const page = paginateGearResults(matches);
    results.hidden = false;
    resultsGrid.innerHTML = page.items.length
      ? page.items.map(item => gearCardMarkup(item, 'search-result-card')).join('')
      : `<article class="analysis-empty"><h2>No product found</h2><p>Try a brand, model family, category, surface, weight or style term.</p></article>`;
    const heading = $('#gear-search-results h2');
    const copy = $('#gear-search-results .brand-section-head p');
    if (heading) heading.textContent = rawQuery ? `Results for “${rawQuery}”` : 'Browse the index';
    if (copy) copy.textContent = `${page.items.length} of ${page.total} shown. Images and prices appear only when source-backed.`;
    if (loadMore) {
      loadMore.hidden = !page.hasMore;
      loadMore.textContent = `Load more products (${page.total - page.items.length} left)`;
    }
  }

  const query = normalizeKey(rawQuery);
  $$('.product-card').forEach(card => {
    const matchesQuery = normalizeKey(card.textContent).includes(query);
    const matchesType = type === 'All' || card.dataset.type === type;
    const matchesBrand = brand === 'All brands' || card.dataset.brand === brand;
    const show = matchesQuery && matchesType && matchesBrand;
    card.style.display = show ? '' : 'none';
  });

  $$('[data-brand-section]').forEach(section => {
    const visibleCards = $$('.product-card', section).filter(card => card.style.display !== 'none');
    const special = ['recommendations', 'continue'].includes(section.dataset.brandSection);
    section.hidden = query ? section.id !== 'gear-search-results' : (!special && visibleCards.length === 0);
  });
}

function gearItemByKey(key) {
  return REAL_GEAR_ITEMS.find(item => productKey(item) === key);
}

function showProductDetail(key = '') {
  const output = $('#store-output');
  const item = gearItemByKey(key);
  if (!output || !item) return;
  rememberGearInterest(item);
  const specs = gearSpecsSummary(item.specs) || 'Specs unavailable';
  const links = gearSourceLinks(item);
  output.innerHTML = `<span class="eyebrow">PRODUCT DETAIL</span>
    <h2>${escapeHtml(gearTitle(item))}</h2>
    <p><b>Category:</b> ${escapeHtml(gearCategory(item))}${item.subcategory ? ` · ${escapeHtml(item.subcategory)}` : ''}</p>
    <p><b>Specs:</b> ${escapeHtml(specs)}</p>
    <p><b>Status:</b> ${escapeHtml(item.status || 'unknown')} · <b>Availability:</b> ${escapeHtml(item.availability || 'unknown')}</p>
    <p><b>Price:</b> ${escapeHtml(gearPriceLabel(item))}</p>
    <p>${escapeHtml(item.game_impact || item.best_for || 'No source-backed game note yet.')}</p>
    <div class="store-actions">
      ${links.length ? links.map((url, index) => `<a target="_blank" rel="noopener noreferrer" href="${escapeHtml(url)}">${index === 0 ? 'Source' : 'Source ' + (index + 1)} ↗</a>`).join('') : '<span>No exact product source link stored yet.</span>'}
    </div>`;
}

function showStorePath(product, key = '') {
  const output = $('#store-output');
  const city = $('#city-input')?.value?.trim() || state.gearLocation || 'your city';
  const mode = $('#buying-mode')?.value || state.gearMode || 'Both';

  const item = gearItemByKey(key);
  if (item) rememberGearInterest(item);

  const searchText = `${product} tennis store ${city}`;
  const url = mode === 'Online'
    ? `https://www.google.com/search?q=${encodeURIComponent(`${product} tennis buy online official retailer`)}`
    : `https://www.google.com/maps/search/${encodeURIComponent(searchText)}`;

  window.open(url, '_blank', 'noopener,noreferrer');

  if (!output) return;
  output.innerHTML = `<span class="eyebrow">SHOPPING</span>
    <h2>${escapeHtml(product)}</h2>
    <p><b>${escapeHtml(mode)}:</b> Opened a real ${mode === 'Online' ? 'web search' : 'map search'} for “${escapeHtml(searchText)}”. Only trust a listing if it clearly shows this exact product or brand category.</p>
    <div class="store-actions">
      <a target="_blank" rel="noopener noreferrer" href="${escapeHtml(url)}">Open again ↗</a>
      ${item && (item.product_url || item.official_url || item.retailer_url) ? `<a target="_blank" rel="noopener noreferrer" href="${escapeHtml(item.product_url || item.official_url || item.retailer_url)}">View Product ↗</a>` : item && BRAND_OFFICIAL_URLS[item.brand] ? `<a target="_blank" rel="noopener noreferrer" href="${escapeHtml(BRAND_OFFICIAL_URLS[item.brand])}">Visit ${escapeHtml(item.brand)} ↗</a>` : ''}
    </div>`;
  toast('Opening store search.');
}

const pages = {
  entry: entryPage,
  trainhome: trainOverviewPage,
  today: trainOverviewPage,
  predict: predictOverviewPage,
  learn: learnPage,
  puzzles: puzzlesPage,
  analyze: analyzePage,
  train: trainPage,
  compete: competePage,
  quant: quantPage,
  players: playersPage,
  compare: comparePage,
  simulation: simulationPage,
  model: modelPage,
  profile: profilePage
};

function updatePlayerResults() {
  const results = $('.results');
  if (!results) return;

  results.innerHTML = playerResultsHtml();
  bindPlayerButtons(results);
  updateSlotTabs();
}

function updateSlotTabs() {
  $$('[data-slot]').forEach(button => {
    button.classList.toggle('active', button.dataset.slot === state.activeSlot);
  });
}

function bindPlayerButtons(root = document) {
  $$('[data-name]', root).forEach(button => {
    button.onclick = () => selectPlayer(button.dataset.name, button.dataset.force || state.activeSlot);
  });
}

function answerPuzzle(choiceIndex) {
  const { puzzle, step, item } = currentPuzzle();
  const bestIndex = item[4];
  const correct = Number(choiceIndex) === bestIndex;
  const selected = item[3][Number(choiceIndex)] || 'Unknown choice';
  const best = item[3][bestIndex];
  const category = puzzle.category || puzzle.name || 'General';
  const stats = state.puzzleStats || { attempted: 0, correct: 0, categories: {} };
  const categoryStats = stats.categories?.[category] || { attempted: 0, correct: 0 };
  stats.attempted += 1;
  categoryStats.attempted += 1;

  if (correct) {
    stats.correct += 1;
    categoryStats.correct += 1;
    state.puzzleFeedback = `Preferred decision: ${selected}. The next ball is easier because your shot protected court position.`;
  } else {
    state.puzzleFeedback = `Risky choice: ${selected}. Better: ${best}. The rally continues, but now you are defending more.`;
  }
  stats.categories = { ...(stats.categories || {}), [category]: categoryStats };
  state.puzzleStats = stats;
  state.puzzleLastChoice = selected;
  state.puzzleLastCorrect = correct;

  state.puzzleStep = Math.min(step + 1, puzzle.steps.length - 1);
  saveState();
  render();
}

function resetPuzzle(id = state.puzzleId) {
  state.puzzleSeed = Number(id) || nextPuzzleSeed();
  state.puzzleId = 0;
  state.puzzleStep = 0;
  state.puzzleFeedback = '';
  state.puzzleLastChoice = '';
  state.puzzleLastCorrect = null;
  saveState();
  render();
}

function startPuzzleTraining() {
  state.puzzleCategory = $('#puzzle-category')?.value || state.puzzleCategory || 'Random';
  state.puzzleDifficulty = $('#puzzle-difficulty')?.value || state.puzzleDifficulty || 'Any difficulty';
  state.puzzleSurface = $('#puzzle-surface')?.value || state.puzzleSurface || 'Any surface';
  resetPuzzle(nextPuzzleSeed());
}

function updatePlanCompletion(id, done) {
  const store = trainStore();
  if (!store.plan.length) store.plan = defaultPlanItems();
  store.plan = store.plan.map(item => item.id === id ? { ...item, done } : item);
  saveTrainStore(store);
  render();
}

function startTrainingSession() {
  const store = trainStore();
  store.activeSession = { id: `session-${Date.now()}`, startedAt: new Date().toISOString(), status: 'in progress' };
  saveTrainStore(store);
  toast('Session started.');
  render();
}

function completeTrainingSession(status = 'completed') {
  const store = trainStore();
  const note = $('#session-note')?.value?.trim() || '';
  const session = store.activeSession || { id: `session-${Date.now()}`, startedAt: new Date().toISOString() };
  store.sessions = [{ ...session, status, note, endedAt: new Date().toISOString() }, ...store.sessions].slice(0, 20);
  store.activeSession = null;
  saveTrainStore(store);
  toast(status === 'completed' ? 'Session saved.' : 'Session skipped.');
  render();
}

function createConfiguredPlan() {
  const latest = latestAnalysis();
  const analysisTags = (latest?.recommendations || []).flatMap(item => TRAINING_GOALS.filter(goal => `${item.title} ${item.saw} ${item.drill}`.toLowerCase().includes(goal.toLowerCase())));
  const plan = generateTrainingPlan({
    goal: $('#plan-goal')?.value,
    level: $('#plan-level')?.value,
    days: Number($('#plan-days')?.value),
    duration: Number($('#plan-duration')?.value),
    weeks: Number($('#plan-weeks')?.value),
    analysisTags
  });
  plan.selectedSessionId = plan.sessions[0]?.id || null;
  const store = trainStore();
  store.activePlan = plan;
  saveTrainStore(store);
  render();
  toast('Training plan generated.');
}

function selectPlanSession(sessionId) {
  const store = trainStore();
  if (!store.activePlan?.sessions?.some(session => session.id === sessionId)) return;
  store.activePlan.selectedSessionId = sessionId;
  saveTrainStore(store);
  render();
}

function togglePlanSession(sessionId) {
  const store = trainStore();
  if (!store.activePlan) return;
  store.activePlan.sessions = store.activePlan.sessions.map(session => session.id === sessionId ? { ...session, status: session.status === 'completed' ? 'upcoming' : 'completed' } : session);
  saveTrainStore(store);
  render();
}

function handleVideoInput(file, options = {}) {
  if (state.selectedVideoUrl) {
    URL.revokeObjectURL(state.selectedVideoUrl);
    state.selectedVideoUrl = '';
  }
  state.selectedVideo = file || null;
  const label = $('#selected-file-name');
  const error = $('#upload-error');
  const button = $('#analyze-btn');
  const empty = $('#video-empty-state');
  const previewState = $('#video-preview-state');
  const preview = $('#selected-video-preview');
  const readiness = $('#readiness-title');
  const facts = $('#readiness-facts');
  const validationError = validateVideoFile(file);
  if (label) label.textContent = file ? file.name : 'No video selected';
  if (error) error.textContent = file && validationError ? validationError : '';
  if (button) button.disabled = !file || Boolean(validationError);
  if (!file || validationError) {
    if (empty) empty.hidden = false;
    if (previewState) previewState.hidden = true;
    if (readiness) readiness.textContent = file ? 'Unsupported footage' : 'Waiting for footage';
    if (facts) facts.innerHTML = '<p>Select a valid video to inspect browser-detectable metadata.</p>';
    return;
  }
  state.selectedVideoUrl = URL.createObjectURL(file);
  if (empty) empty.hidden = true;
  if (previewState) previewState.hidden = false;
  if (preview) {
    preview.src = state.selectedVideoUrl;
    preview.load();
    preview.onloadedmetadata = () => {
      const duration = Number.isFinite(preview.duration) ? `${preview.duration.toFixed(1)} sec` : 'Duration unavailable';
      const resolution = preview.videoWidth && preview.videoHeight ? `${preview.videoWidth} × ${preview.videoHeight}` : 'Resolution unavailable';
      const details = `${duration} · ${resolution} · ${(file.size / 1024 / 1024).toFixed(1)} MB`;
      const meta = $('#selected-video-details');
      if (meta) meta.textContent = details;
      if (facts) facts.innerHTML = `<p><b>Video loaded</b></p><p>${escapeHtml(duration)}</p><p>${escapeHtml(resolution)}</p><p>${(file.size / 1024 / 1024).toFixed(1)} MB</p><p><b>Ready for analysis</b></p>`;
    };
    preview.onerror = () => {
      const message = 'The browser could not decode this video. Try an H.264 MP4, MOV, M4V or WebM file.';
      if (error) error.textContent = message;
      if (button) button.disabled = true;
      if (readiness) readiness.textContent = 'Video could not be decoded';
    };
  }
  if (readiness) readiness.textContent = 'Ready for analysis';
  if (!options.silent) toast('Video ready to analyze.');
}

function bindPageEvents() {
  $('#p1')?.addEventListener('input', event => handleTopInput('player1', event.target.value));
  $('#p2')?.addEventListener('input', event => handleTopInput('player2', event.target.value));
  $('#p1')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      if (commitField('player1')) render();
    }
  });
  $('#p2')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      if (commitField('player2')) render();
    }
  });

  $('#slam')?.addEventListener('change', event => {
    state.slam = event.target.value;
    state.backendPrediction = null;
    state.predictionError = '';
    saveState();
    render();
  });

  const runPredictionClick = async () => {
    const ok1 = commitField('player1');
    const ok2 = commitField('player2');
    if (!ok1 || !ok2) return;
    state.predictionLoading = true;
    state.predictionError = '';
    state.backendPrediction = null;
    render();
    toast('Model running.');
    try {
      await checkBackendHealth();
      state.backendPrediction = await runBackendPrediction();
      state.predictionError = '';
      toast('Prediction ready.');
    } catch (error) {
      state.backendPrediction = null;
      state.predictionError = readableApiError(error);
      toast('Prediction needs backend data.');
    } finally {
      state.predictionLoading = false;
    }
    render();
  };

  $('#predict')?.addEventListener('click', runPredictionClick);
  $('#retry-predict')?.addEventListener('click', runPredictionClick);

  $$('[data-tour]').forEach(button => {
    button.onclick = event => {
      event.preventDefault();
      event.stopPropagation();
      const nextTour = tourKey(button.dataset.tour);
      if (state.page === 'compete') {
        state.selectedTour = nextTour;
        saveState();
        render();
        return;
      }
      state.selectedTour = nextTour;
      state.player1 = fallbackPlayer(nextTour, '');
      state.player2 = fallbackPlayer(nextTour, state.player1);
      state.draftP1 = state.player1;
      state.draftP2 = state.player2;
      state.activeSlot = 'player1';
      state.search = '';
      state.backendPrediction = null;
      state.predictionError = '';
      saveState();
      render();
    };
  });

  $$('[data-slot]').forEach(button => {
    button.onclick = () => {
      state.activeSlot = button.dataset.slot;
      state.search = '';
      render();
    };
  });

  $('#finder')?.addEventListener('input', event => {
    state.search = event.target.value;
    updatePlayerResults();
  });

  bindPlayerButtons();
  $$('.choice').forEach(button => {
    button.onclick = () => {
      const group = button.closest('.choice-list');
      if (group) $$('.choice', group).forEach(choice => choice.classList.remove('active'));
      button.classList.add('active');
      toast('Selection updated.');
    };
  });
  $$('button[data-learn-level]').forEach(button => {
    button.onclick = () => {
      if (!LEARN_CURRICULUM[button.dataset.learnLevel]) return;
      const level = button.dataset.learnLevel;
      updateLearnView({ learnLevel: level, learnCategory: LEARN_CURRICULUM[level][0].id, learnOpenLesson: '' });
    };
  });
  $$('button[data-learn-category]').forEach(button => {
    button.onclick = () => {
      if (!curriculumFor().some(category => category.id === button.dataset.learnCategory)) return;
      updateLearnView({ learnCategory: button.dataset.learnCategory, learnOpenLesson: '' });
    };
  });
  $$('button[data-learn-open], button[data-learn-related]').forEach(button => {
    button.onclick = () => {
      const lessonId = button.dataset.learnOpen || button.dataset.learnRelated;
      const found = findLearnLesson(lessonId);
      if (!found) return;
      state.learnLesson = found.lesson.visual || state.learnLesson;
      state.learnStep = 1;
      updateLearnView({ learnCategory: found.category.id, learnOpenLesson: lessonId });
    };
  });
  $$('button[data-learn-back]').forEach(button => {
    button.onclick = () => {
      updateLearnView({ learnOpenLesson: '' });
    };
  });
  $$('button[data-learn-choice]').forEach(button => {
    button.onclick = () => {
      const lesson = LEARN_COACHING[state.learnLesson];
      if (!lesson?.feedback?.[button.dataset.learnChoice]) return;
      state.learnChoice[state.learnLesson] = button.dataset.learnChoice;
      state.learnStep = 2;
      render();
    };
  });
  $$('button[data-learn-step]').forEach(button => {
    button.onclick = () => {
      state.learnStep = Math.max(1, Math.min(3, Number(button.dataset.learnStep) || 1));
      render();
    };
  });

  $$('input[type="file"]').forEach(input => {
    input.onchange = () => {
      if (input.id === 'video-upload') {
        const selectedFile = input.files?.[0] || null;
        state.selectedVideo = selectedFile;
        if (state.page !== 'analyze' || location.hash !== '#train/analyze') {
          applyRoute('train/analyze', { replace: true });
        }
        handleVideoInput(selectedFile);
      }
      if (input.id === 'photo-input') {
        const preview = $('#photo-preview');
        if (preview) preview.innerHTML = Array.from(input.files || []).slice(0, 5).map(file => `<span>${escapeHtml(file.name)}</span>`).join('');
      }
      if (input.files?.length) toast(`${input.files.length} file${input.files.length > 1 ? 's' : ''} selected.`);
    };
  });

  $('#analyze-btn')?.addEventListener('click', analyzeUploadedVideo);
  $('#remove-video')?.addEventListener('click', () => {
    const input = $('#video-upload');
    if (input) input.value = '';
    handleVideoInput(null);
  });
  const dropZone = $('#drop-zone');
  const videoInput = $('#video-upload');
  if (dropZone && videoInput) {
    ['dragenter', 'dragover'].forEach(type => dropZone.addEventListener(type, event => {
      event.preventDefault();
      dropZone.classList.add('dragging');
    }));
    ['dragleave', 'drop'].forEach(type => dropZone.addEventListener(type, event => {
      event.preventDefault();
      dropZone.classList.remove('dragging');
    }));
    dropZone.addEventListener('drop', event => {
      const file = event.dataTransfer?.files?.[0] || null;
      if (file) handleVideoInput(file);
    });
  }
  $$('[data-video-time]').forEach(button => {
    button.onclick = () => {
      const video = $('#analysis-video');
      if (video) {
        video.currentTime = Number(button.dataset.videoTime || 0);
        video.play?.().catch(() => undefined);
      }
    };
  });
  $('#add-analysis-plan')?.addEventListener('click', () => {
    const added = addAnalysisToPlan();
    toast(added ? 'Added to training plan.' : 'Analyze a clip first.');
    if (state.page === 'train') render();
  });
  $$('.plan-check').forEach(input => {
    input.onchange = () => updatePlanCompletion(input.dataset.planId, input.checked);
  });
  $('#start-session')?.addEventListener('click', startTrainingSession);
  $('#complete-session')?.addEventListener('click', () => completeTrainingSession('completed'));
  $('#skip-session')?.addEventListener('click', () => completeTrainingSession('skipped'));
  if ($('#generate-plan')) $('#generate-plan').onclick = createConfiguredPlan;
  if ($('#replace-plan')) $('#replace-plan').onclick = createConfiguredPlan;
  $$('[data-session-complete]').forEach(button => button.addEventListener('click', () => togglePlanSession(button.dataset.sessionComplete)));
  $$('[data-plan-session]').forEach(button => button.addEventListener('click', () => selectPlanSession(button.dataset.planSession)));
  $('#local-profile-reset')?.addEventListener('click', () => {
    ['cqP1', 'cqP2', 'cqProduct', 'cqLastTrainRoute', 'cqLastPredictRoute'].forEach(key => localStorage.removeItem(key));
    toast('Local profile session cleared.');
  });
  $$('[data-puzzle-answer]').forEach(button => {
    button.onclick = () => answerPuzzle(button.dataset.puzzleAnswer);
  });
  $('#reset-puzzle')?.addEventListener('click', () => resetPuzzle());
  $('#next-puzzle')?.addEventListener('click', () => resetPuzzle(nextPuzzleId()));
  $('#start-puzzle-training')?.addEventListener('click', startPuzzleTraining);
  $('#puzzle-category')?.addEventListener('change', event => {
    state.puzzleCategory = event.target.value;
    saveState();
    resetPuzzle(nextPuzzleId());
  });
  $('#puzzle-difficulty')?.addEventListener('change', event => {
    state.puzzleDifficulty = event.target.value;
    saveState();
    resetPuzzle(nextPuzzleId());
  });
  $('#puzzle-surface')?.addEventListener('change', event => {
    state.puzzleSurface = event.target.value;
    saveState();
    resetPuzzle(nextPuzzleId());
  });
  $('#city-input')?.addEventListener('input', event => {
    state.gearLocation = event.target.value;
    saveState();
  });
  $('#city-input')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      state.gearLocation = event.target.value.trim();
      saveState();
      toast('Location updated.');
    }
  });
  $('#gear-search')?.addEventListener('input', () => {
    state.gearPage = 1;
    updateGearCards();
  });
  $('#gear-search')?.addEventListener('keydown', event => {
    if (event.key === 'Enter') {
      event.preventDefault();
      updateGearCards();
    }
  });
  $('#clear-gear-search')?.addEventListener('click', () => {
    state.gearQuery = '';
    state.gearPage = 1;
    const input = $('#gear-search');
    if (input) input.value = '';
    updateGearCards();
  });
  $('#buying-mode')?.addEventListener('change', updateGearCards);
  $('#brand-filter')?.addEventListener('change', () => {
    state.gearPage = 1;
    updateGearCards();
  });
  $('#load-more-gear')?.addEventListener('click', () => {
    state.gearPage = (state.gearPage || 1) + 1;
    updateGearCards();
  });
  $('#reset-gear-memory')?.addEventListener('click', () => {
    localStorage.removeItem('cqGearInterest');
    state.gearQuery = '';
    state.gearBrand = 'All brands';
    state.gearType = 'All';
    toast('Gear preferences reset.');
    render();
  });
  $$('.gear-filter').forEach(button => {
    button.onclick = () => {
      $$('.gear-filter').forEach(filter => filter.classList.remove('active'));
      button.classList.add('active');
      state.gearType = button.dataset.gearType || 'All';
      state.gearPage = 1;
      updateGearCards();
    };
  });
  const pageRoot = $('#page');
  if (pageRoot) pageRoot.onclick = event => {
    const storeButton = event.target.closest('.store-btn');
    if (storeButton) showStorePath(storeButton.dataset.product, storeButton.dataset.key);
    const detailButton = event.target.closest('.detail-btn');
    if (detailButton) showProductDetail(detailButton.dataset.key);
  };

  $('#ask-ai')?.addEventListener('click', () => toast('Coaching guidance is available in Learn and Analyze.'));
	}

function render() {
  let route = normalizeRoute(state.route || location.hash.slice(1) || state.page);
  if (!pages[route.page]) route = ROUTE_BY_ID.get('entry');
  state.route = route.id;
  state.page = route.page;
  state.product = route.product === 'entry' ? (state.product || localStorage.cqProduct || 'train') : route.product;
  const pageRoot = $('#page');
  const existingPlanBuilder = state.page === 'train' ? $('.plan-builder', pageRoot) : null;
  const nextMarkup = pages[state.page]();
  if (existingPlanBuilder) {
    const nextPage = document.createElement('div');
    nextPage.innerHTML = nextMarkup;
    const generatedPlanBuilder = $('.plan-builder', nextPage);
    if (generatedPlanBuilder) generatedPlanBuilder.replaceWith(existingPlanBuilder);
    pageRoot.replaceChildren(...nextPage.childNodes);
  } else {
    pageRoot.innerHTML = nextMarkup;
  }
  document.body.dataset.product = state.product;
  document.body.dataset.page = state.page;
  document.body.classList.toggle('entry-mode', state.page === 'entry');
  $$('[data-product]').forEach(button => button.classList.toggle('active', button.dataset.product === state.product));
  $$('[data-nav-product]').forEach(group => group.hidden = state.page !== 'entry' && group.dataset.navProduct !== state.product);
  $$('nav button').forEach(button => {
    button.classList.toggle('active', normalizeRoute(button.dataset.page).id === state.route);
  });
  bindPageEvents();
  if (state.page === 'analyze' && state.selectedVideo) handleVideoInput(state.selectedVideo, { silent: true });
}

window.addEventListener('hashchange', () => {
  const route = normalizeRoute(location.hash.slice(1) || 'entry');
  state.route = route.id;
  state.page = route.page;
  state.product = route.product === 'entry' ? (state.product || localStorage.cqProduct || 'train') : route.product;
  if (route.id !== (location.hash.slice(1) || 'entry')) {
    syncHash(route, true);
  }
  render();
});

window.addEventListener('popstate', event => {
  const learn = event.state?.courtiqLearn;
  if (!learn || state.page !== 'learn' || !LEARN_CURRICULUM[learn.level]) return;
  state.learnLevel = learn.level;
  state.learnCategory = learn.category || LEARN_CURRICULUM[learn.level][0].id;
  state.learnOpenLesson = findLearnLesson(learn.lesson, learn.level) ? learn.lesson : '';
  localStorage.cqLearnLevel = state.learnLevel;
  render();
});

document.addEventListener('click', handleRouteIntent);
render();
