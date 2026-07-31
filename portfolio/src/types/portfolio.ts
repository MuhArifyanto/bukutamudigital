export type ProjectCategory = 'all' | 'action-combat' | 'custom-engine' | 'ai-physics' | 'shaders-vfx';

export interface CodeSnippet {
  title: string;
  language: 'cpp' | 'csharp' | 'hlsl';
  code: string;
  description: string;
}

export interface MetricItem {
  label: string;
  value: string;
  subtext: string;
}

export interface Project {
  id: string;
  title: string;
  subtitle: string;
  category: 'action-combat' | 'custom-engine' | 'ai-physics' | 'shaders-vfx';
  engine: string;
  role: string;
  year: string;
  summary: string;
  detailedDescription: string;
  bannerImage: string;
  accentColor: 'cyan' | 'purple' | 'yellow' | 'pink';
  features: string[];
  metrics: MetricItem[];
  architectureHighlights: {
    title: string;
    description: string;
  }[];
  codeSnippet: CodeSnippet;
  tags: string[];
  playableDemoUrl?: string;
  githubUrl?: string;
}

export interface ComboStateNode {
  id: string;
  name: string;
  inputTrigger: string;
  startupFrames: number;
  activeFrames: number;
  recoveryFrames: number;
  cancelWindowStartFrame: number;
  damage: number;
  poiseDamage: number;
  hitType: 'Light Slash' | 'Heavy Cleave' | 'Parry Counter' | 'Finisher';
  description: string;
  nextStates: string[];
}

export interface TechItem {
  name: string;
  level: number;
  experienceYears: string;
  tag: string;
  highlights: string[];
}

export interface TechCategory {
  id: string;
  title: string;
  subtitle: string;
  icon: string;
  color: 'cyan' | 'purple' | 'yellow';
  items: TechItem[];
}

export interface CodePattern {
  id: string;
  title: string;
  patternName: string;
  language: 'cpp' | 'csharp';
  engine: 'Unreal Engine 5' | 'Custom Engine' | 'Unity';
  summary: string;
  code: string;
  architectureBreakdown: string[];
}
