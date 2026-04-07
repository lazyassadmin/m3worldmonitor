export declare const SEVERITY_SCORE: Record<string, number>;
export declare const THREAT_LEVEL: Record<string, number>;
export declare function warningComponent(warningCount: number): number;
export declare function aisComponent(maxCongestionSeverity: number): number;
export declare function computeDisruptionScore(
	threatLevel: number,
	warningCount: number,
	maxCongestionSeverity: number,
): number;
export declare function scoreToStatus(score: number): string;
export declare function computeHHI(shares: number[]): number;
export declare function riskRating(hhi: number): string;
export declare function detectTrafficAnomaly(
	history: Array<{ date: string; total: number }>,
	threatLevel: string,
): { dropPct: number; signal: boolean };
export declare function detectSpike(history: Array<number | { value: number }>): boolean;
