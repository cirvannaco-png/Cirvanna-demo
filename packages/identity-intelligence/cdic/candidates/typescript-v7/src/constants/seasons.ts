import { ValidSeason } from '../types/core';

export const VALID_SEASONS = Object.freeze(['spring', 'summer', 'fall', 'winter']) as readonly ValidSeason[];

export const SEASON_MAP: Readonly<Record<number, ValidSeason>> = Object.freeze({
  0: 'winter', 1: 'winter', 2: 'spring',
  3: 'spring', 4: 'spring', 5: 'summer',
  6: 'summer', 7: 'summer', 8: 'fall',
  9: 'fall', 10: 'fall', 11: 'winter'
});
