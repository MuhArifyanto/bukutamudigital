import React from 'react';
import { Shield, ChevronRight, Cpu, Zap, Terminal, Activity, ArrowDown } from 'lucide-react';
import { HERO_STATS } from '../data/portfolioData';

interface HeroProps {
  onExploreCombatClick: () => void;
  onExploreProjectsClick: () => void;
}

export const Hero: React.FC<HeroProps> = ({ onExploreCombatClick, onExploreProjectsClick }) => {
  return (
    <section id="hero" className="relative min-h-screen pt-28 pb-16 flex items-center justify-center overflow-hidden bg-cyber-grid scanlines">
      {/* Background Radial Glow */}
      <div className="absolute inset-0 bg-radial-gradient pointer-events-none"></div>
      
      {/* Corner HUD Decors */}
      <div className="absolute top-24 left-6 hidden md:block text-[10px] font-mono text-cyan-500/40 space-y-1">
        <div>[SYS_LATENCY: 4.2ms]</div>
        <div>[RENDER_TARGET: 144Hz]</div>
        <div>[PHYSICS_TICK: FIXED_STEP]</div>
      </div>
      <div className="absolute top-24 right-6 hidden md:block text-[10px] font-mono text-purple-400/40 text-right space-y-1">
        <div>[ENGINE: UNREAL_5 / CUSTOM_C++]</div>
        <div>[INPUT_BUFFER: ACTIVE]</div>
        <div>[MEMORY_POOL: ZERO_ALLOC]</div>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10 w-full">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          
          {/* Main Hero Column */}
          <div className="lg:col-span-7 space-y-8">
            
            {/* Status Badge */}
            <div className="inline-flex items-center space-x-2 px-3 py-1.5 rounded-full bg-[#0c101c] border border-cyan-500/40 text-xs font-mono glow-cyan">
              <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping"></span>
              <span className="text-cyan-400 font-semibold tracking-wide">GAMEPLAY SYSTEMS & COMBAT ARCHITECT</span>
            </div>

            {/* Main Headline */}
            <div className="space-y-4">
              <h1 className="text-4xl sm:text-6xl lg:text-7xl font-extrabold tracking-tight text-white leading-tight font-display">
                DYNAMIC <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 via-purple-500 to-yellow-300 text-glow-cyan">COMBAT</span>
                <br />
                & ENGINE ARCHITECTURE
              </h1>
              <p className="text-slate-300 text-base sm:text-lg max-w-2xl leading-relaxed">
                Specializing in responsive combat mechanics, frame-accurate input buffering, deterministic state machines, and high-performance C++ / C# game engines.
              </p>
            </div>

            {/* Quick Tech Badges */}
            <div className="flex flex-wrap gap-2 text-xs font-mono text-slate-300">
              {['Unreal Engine 5 (C++)', 'Frame-Accurate Combos', 'Spatial Hashing', 'Utility AI', 'Shader Graph / HLSL'].map((tech, idx) => (
                <span key={idx} className="px-2.5 py-1 bg-[#0c101c] border border-slate-800 rounded text-slate-300 flex items-center gap-1.5">
                  <span className="text-cyan-400">#</span> {tech}
                </span>
              ))}
            </div>

            {/* CTAs */}
            <div className="flex flex-wrap gap-4 pt-2">
              <button
                onClick={onExploreCombatClick}
                className="px-6 py-3.5 bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-slate-950 font-bold font-mono text-xs tracking-wider rounded glow-cyan flex items-center space-x-2.5 transition-all transform hover:-translate-y-0.5 active:translate-y-0"
              >
                <Shield className="w-4 h-4" />
                <span>EXECUTE_COMBAT_DEMO</span>
                <ChevronRight className="w-4 h-4" />
              </button>

              <button
                onClick={onExploreProjectsClick}
                className="px-6 py-3.5 bg-[#0c101c] hover:bg-slate-900 border border-purple-500/40 hover:border-purple-400 text-purple-300 font-bold font-mono text-xs tracking-wider rounded glow-purple flex items-center space-x-2.5 transition-all"
              >
                <Cpu className="w-4 h-4 text-purple-400" />
                <span>INSPECT_PROJECTS</span>
              </button>
            </div>

          </div>

          {/* Telemetry / Live HUD Graphic Card */}
          <div className="lg:col-span-5">
            <div className="relative bg-[#0c101c]/90 border border-cyan-500/30 rounded-xl p-6 glow-cyan hud-box backdrop-blur space-y-6">
              
              {/* Card Header */}
              <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-mono">
                <div className="flex items-center space-x-2">
                  <Terminal className="w-4 h-4 text-cyan-400" />
                  <span className="text-xs text-slate-200 font-bold">COMBAT ENGINE TELEMETRY</span>
                </div>
                <span className="text-[10px] text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded border border-emerald-500/30">LIVE_TICK</span>
              </div>

              {/* Engine State Indicator */}
              <div className="space-y-4">
                <div className="bg-[#05070d] p-4 rounded border border-slate-800/80 space-y-3 font-mono">
                  <div className="flex justify-between items-center text-xs">
                    <span className="text-slate-400">STATE_MACHINE:</span>
                    <span className="text-yellow-400 font-bold">CANCEL_WINDOW_ACTIVE</span>
                  </div>
                  <div className="w-full bg-slate-800 h-2 rounded-full overflow-hidden">
                    <div className="bg-gradient-to-r from-cyan-400 to-purple-500 h-full w-[70%] animate-pulse"></div>
                  </div>
                  <div className="grid grid-cols-3 text-[10px] text-slate-400 pt-1 border-t border-slate-800/50">
                    <div>STARTUP: <span className="text-white">4f</span></div>
                    <div>ACTIVE: <span className="text-cyan-400 font-bold">3f</span></div>
                    <div>RECOVERY: <span className="text-purple-400">8f</span></div>
                  </div>
                </div>

                {/* Input Buffer Live Feed */}
                <div className="space-y-2">
                  <div className="text-[11px] font-mono text-slate-400 flex items-center justify-between">
                    <span>INPUT_BUFFER_QUEUE:</span>
                    <span className="text-cyan-400 text-[10px]">16.6ms window</span>
                  </div>
                  <div className="grid grid-cols-4 gap-2 text-[10px] font-mono">
                    <div className="bg-cyan-500/20 border border-cyan-500/40 p-2 rounded text-center text-cyan-300">
                      [J] LIGHT_01
                    </div>
                    <div className="bg-purple-500/20 border border-purple-500/40 p-2 rounded text-center text-purple-300">
                      [K] HEAVY_02
                    </div>
                    <div className="bg-yellow-500/20 border border-yellow-500/40 p-2 rounded text-center text-yellow-300 animate-pulse">
                      [SPACE] DODGE
                    </div>
                    <div className="bg-slate-900 border border-slate-800 p-2 rounded text-center text-slate-600">
                      EMPTY
                    </div>
                  </div>
                </div>
              </div>

              {/* Bottom System Metrics */}
              <div className="grid grid-cols-2 gap-3 pt-2 font-mono">
                <div className="bg-[#05070d] p-2.5 rounded border border-slate-800">
                  <p className="text-[10px] text-slate-400">SPATIAL_SWEEP</p>
                  <p className="text-xs font-bold text-cyan-400">0.12ms / tick</p>
                </div>
                <div className="bg-[#05070d] p-2.5 rounded border border-slate-800">
                  <p className="text-[10px] text-slate-400">MEMORY_ALLOC</p>
                  <p className="text-xs font-bold text-emerald-400">0 KB / frame</p>
                </div>
              </div>

            </div>
          </div>

        </div>

        {/* Hero Stats Ribbon */}
        <div className="mt-16 grid grid-cols-2 md:grid-cols-4 gap-4 pt-8 border-t border-slate-800/80">
          {HERO_STATS.map((stat, idx) => (
            <div key={idx} className="bg-[#0c101c]/60 border border-slate-800/80 p-4 rounded-lg font-mono">
              <p className="text-2xl sm:text-3xl font-extrabold text-cyan-400 text-glow-cyan">{stat.value}</p>
              <p className="text-xs font-bold text-slate-200 mt-1">{stat.label}</p>
              <p className="text-[10px] text-slate-400 mt-0.5">{stat.subtext}</p>
            </div>
          ))}
        </div>

        {/* Scroll Indicator */}
        <div className="flex justify-center mt-12">
          <button 
            onClick={onExploreCombatClick}
            className="text-slate-400 hover:text-cyan-400 transition-colors flex flex-col items-center gap-1.5 text-xs font-mono group"
          >
            <span>SCROLL_FOR_COMBAT_ENGINE</span>
            <ArrowDown className="w-4 h-4 group-hover:translate-y-1 transition-transform text-cyan-400" />
          </button>
        </div>

      </div>
    </section>
  );
};
