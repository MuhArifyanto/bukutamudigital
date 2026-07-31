import React, { useState } from 'react';
import { Activity, Cpu, Swords, Zap, CheckCircle2, ChevronRight, Layers, ArrowRight } from 'lucide-react';
import { TECH_STACK } from '../data/portfolioData';

export const ArchitectureSection: React.FC = () => {
  const [activeTabId, setActiveTabId] = useState<string>('core-engines');

  const activeCategory = TECH_STACK.find(t => t.id === activeTabId) || TECH_STACK[0];

  return (
    <section id="architecture" className="py-24 relative bg-[#06080e] border-t border-slate-800/80">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-16">
        
        {/* Section Header */}
        <div className="text-center space-y-4 max-w-3xl mx-auto">
          <div className="inline-flex items-center space-x-2 px-3 py-1 bg-yellow-500/10 border border-yellow-500/30 rounded-full text-xs font-mono text-yellow-400">
            <Activity className="w-3.5 h-3.5" />
            <span>SYSTEM ARCHITECTURE & TECH MATRIX</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white font-display tracking-tight">
            ENGINEERING <span className="text-yellow-400 text-glow-yellow">STACK & PIPELINES</span>
          </h2>
          <p className="text-slate-400 text-sm sm:text-base">
            Deep technical expertise across AAA game engines, low-level custom architecture, data-driven systems design, and performance profiling.
          </p>
        </div>

        {/* System Architecture Flow Diagram */}
        <div className="bg-[#0c101c] border border-cyan-500/30 rounded-xl p-8 space-y-6 glow-cyan font-mono hud-box">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between border-b border-slate-800 pb-4 gap-2">
            <div>
              <span className="text-[10px] text-cyan-400 uppercase tracking-widest">COMBAT ENGINE PIPELINE SPECIFICATION</span>
              <h3 className="text-lg font-bold text-white font-display">EVENT-DRIVEN COMBAT EXECUTION PIPELINE</h3>
            </div>
            <span className="text-xs bg-cyan-500/10 text-cyan-400 px-3 py-1 rounded border border-cyan-500/30 self-start sm:self-auto">
              TICK_RATE: 120Hz FIXED
            </span>
          </div>

          {/* Interactive Pipeline Diagram Nodes */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
            
            {/* Node 1 */}
            <div className="bg-[#05070d] p-4 rounded-lg border border-slate-800 space-y-2 relative group hover:border-cyan-500/50 transition-colors">
              <div className="text-[10px] text-cyan-400 font-bold">01. INPUT BUFFER</div>
              <p className="font-bold text-white">Ring Buffer Queue</p>
              <p className="text-[11px] text-slate-400 font-sans">Enqueues raw key/gamepad events with 16.6ms window and priority checks.</p>
              <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 text-cyan-400 z-10">
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>

            {/* Node 2 */}
            <div className="bg-[#05070d] p-4 rounded-lg border border-slate-800 space-y-2 relative group hover:border-purple-500/50 transition-colors">
              <div className="text-[10px] text-purple-400 font-bold">02. COMBAT STATE MACHINE</div>
              <p className="font-bold text-white">State Transition Evaluator</p>
              <p className="text-[11px] text-slate-400 font-sans">Validates cancel windows, checks poise/stamina costs, and triggers AnimMontage.</p>
              <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 text-purple-400 z-10">
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>

            {/* Node 3 */}
            <div className="bg-[#05070d] p-4 rounded-lg border border-slate-800 space-y-2 relative group hover:border-yellow-500/50 transition-colors">
              <div className="text-[10px] text-yellow-400 font-bold">03. ANIM NOTIFY & SWEEP</div>
              <p className="font-bold text-white">Socket Trajectory Sweep</p>
              <p className="text-[11px] text-slate-400 font-sans">AnimNotifyState enables capsule sweep between previous & current frame sockets.</p>
              <div className="hidden md:block absolute -right-3 top-1/2 -translate-y-1/2 text-yellow-400 z-10">
                <ArrowRight className="w-4 h-4" />
              </div>
            </div>

            {/* Node 4 */}
            <div className="bg-[#05070d] p-4 rounded-lg border border-slate-800 space-y-2 group hover:border-emerald-500/50 transition-colors">
              <div className="text-[10px] text-emerald-400 font-bold">04. IMPACT RESPONSE</div>
              <p className="font-bold text-white">Poise & Hit-Stop Feedback</p>
              <p className="text-[11px] text-slate-400 font-sans">Applies damage, camera shake, freeze frames, and direction stagger reactions.</p>
            </div>

          </div>
        </div>

        {/* Category Tabs & Tech Breakdown */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Category List */}
          <div className="lg:col-span-4 space-y-3 font-mono">
            <span className="text-[10px] text-slate-400 uppercase tracking-widest px-2">SELECT DOMAIN:</span>
            {TECH_STACK.map((cat) => {
              const isActive = cat.id === activeTabId;
              return (
                <button
                  key={cat.id}
                  onClick={() => setActiveTabId(cat.id)}
                  className={`w-full text-left p-4 rounded-xl border transition-all flex items-center justify-between ${
                    isActive
                      ? 'bg-[#0c101c] border-yellow-400/60 text-white glow-yellow'
                      : 'bg-[#05070d] border-slate-800/80 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                  }`}
                >
                  <div className="space-y-1">
                    <p className={`text-xs font-bold ${isActive ? 'text-yellow-400' : 'text-slate-300'}`}>{cat.title}</p>
                    <p className="text-[10px] text-slate-400 font-sans">{cat.subtitle}</p>
                  </div>
                  <ChevronRight className={`w-4 h-4 ${isActive ? 'text-yellow-400 translate-x-1' : 'text-slate-600'} transition-transform`} />
                </button>
              );
            })}
          </div>

          {/* Right Skill Items Breakdown */}
          <div className="lg:col-span-8 bg-[#0c101c] border border-slate-800 rounded-xl p-8 space-y-6">
            <div className="border-b border-slate-800 pb-4 font-mono">
              <h3 className="text-lg font-bold text-white font-display">{activeCategory.title}</h3>
              <p className="text-xs text-slate-400 font-sans">{activeCategory.subtitle}</p>
            </div>

            <div className="space-y-6">
              {activeCategory.items.map((item, idx) => (
                <div key={idx} className="bg-[#05070d] p-5 rounded-lg border border-slate-800/80 space-y-4 font-mono">
                  
                  {/* Skill Header */}
                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                    <div>
                      <div className="flex items-center space-x-2">
                        <span className="text-sm font-bold text-white">{item.name}</span>
                        <span className="text-[10px] bg-yellow-500/10 text-yellow-400 px-2 py-0.5 rounded border border-yellow-500/30">
                          {item.tag}
                        </span>
                      </div>
                      <span className="text-[10px] text-slate-400 font-sans">{item.experienceYears} Practical Experience</span>
                    </div>

                    {/* Level Bar */}
                    <div className="w-full sm:w-44 space-y-1">
                      <div className="flex justify-between text-[10px] text-slate-400">
                        <span>PROFICIENCY</span>
                        <span className="text-yellow-400 font-bold">{item.level}%</span>
                      </div>
                      <div className="w-full bg-slate-900 h-2 rounded-full overflow-hidden border border-slate-800">
                        <div className="bg-gradient-to-r from-yellow-500 to-amber-400 h-full rounded-full" style={{ width: `${item.level}%` }}></div>
                      </div>
                    </div>
                  </div>

                  {/* Highlights Grid */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-300 font-sans pt-1 border-t border-slate-800/50">
                    {item.highlights.map((hl, hIdx) => (
                      <div key={hIdx} className="flex items-center space-x-2">
                        <CheckCircle2 className="w-3.5 h-3.5 text-yellow-400 flex-shrink-0" />
                        <span className="text-[11px]">{hl}</span>
                      </div>
                    ))}
                  </div>

                </div>
              ))}
            </div>

          </div>

        </div>

      </div>
    </section>
  );
};
