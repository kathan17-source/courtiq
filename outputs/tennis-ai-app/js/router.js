export const ROUTE_DEFINITIONS = [
  ['entry', 'entry', 'entry', ['home']],
  ['train/overview', 'trainhome', 'train', ['trainhome', 'today', 'overview']],
  ['train/analyze', 'analyze', 'train', ['analyze']], ['train/plan', 'train', 'train', ['train']],
  ['train/learn', 'learn', 'train', ['learn']], ['train/puzzles', 'puzzles', 'train', ['puzzles', 'puzzle', 'train/puzzle']],
  ['train/profile', 'profile', 'train', ['profile']], ['predict/overview', 'predict', 'predict', ['predict']],
  ['predict/match', 'quant', 'predict', ['quant', 'match']], ['predict/players', 'players', 'predict', ['players']],
  ['predict/compare', 'compare', 'predict', ['compare']], ['predict/tournaments', 'compete', 'predict', ['compete', 'tournaments']],
  ['predict/simulation', 'simulation', 'predict', ['simulation']], ['predict/model-lab', 'model', 'predict', ['model', 'model-lab']],
  ['privacy', 'privacy', 'entry', []], ['terms', 'terms', 'entry', []]
].map(([id, page, product, aliases]) => ({ id, page, product, aliases }));

export const ROUTE_BY_ID = new Map(ROUTE_DEFINITIONS.map(route => [route.id, route]));
export const ROUTE_BY_PAGE = new Map(ROUTE_DEFINITIONS.map(route => [route.page, route]));
const ROUTE_BY_ALIAS = new Map();
ROUTE_DEFINITIONS.forEach(route => [route.id, route.page, ...route.aliases].forEach(alias => ROUTE_BY_ALIAS.set(alias, route)));

export function normalizeRoute(value) {
  const raw = String(value || '').replace(/^#/, '').replace(/^\/+/, '').trim().toLowerCase();
  if (!raw) return ROUTE_BY_ID.get('entry');
  if (raw === 'gear' || raw === 'train/gear') return ROUTE_BY_ID.get('train/overview');
  return ROUTE_BY_ALIAS.get(raw) || ROUTE_BY_ID.get(raw) || ROUTE_BY_ID.get('entry');
}

export function defaultRouteForProduct(product) {
  return product === 'predict' ? ROUTE_BY_ID.get('predict/overview') : ROUTE_BY_ID.get('train/overview');
}
