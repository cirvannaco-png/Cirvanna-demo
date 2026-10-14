import { CriticalRegion } from '../types/core';

export const CRITICAL_REGIONS = Object.freeze(['head', 'torso', 'arms', 'legs']) as readonly CriticalRegion[];
export const DEFAULT_CRITICAL = Object.freeze(['head', 'torso', 'legs']) as readonly CriticalRegion[];
