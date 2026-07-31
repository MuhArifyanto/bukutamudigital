import React, { useState } from 'react';
import { Code, Copy, Check, Terminal, Layers, Play } from 'lucide-react';
import { CODE_PATTERNS } from '../data/portfolioData';

export const CodeSandbox: React.FC = () => {
  const [selectedPatternId, setSelectedPatternId] = useState<string>(CODE_PATTERNS[0].id);
  const [copied, setCopied] = useState<boolean>(false);

  const activePattern = CODE_PATTERNS.find(p => p.id === selectedPatternId) || CODE_PATTERNS[0];

  const handleCopyCode = () => {
    navigator.clipboard.writeText(activePattern.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section id="code-sandbox" className="py-24 relative bg-[#05070d]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-12">
        
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-end justify-between space-y-4 md:space-y-0">
          <div className="space-y-3">
            <div className="inline-flex items-center space-x-2 px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-xs font-mono text-cyan-400">
              <Code className="w-3.5 h-3.5" />
              <span>CODE PATTERNS & ARCHITECTURE</span>
            </div>
            <h2 className="text-3xl sm:text-5xl font-extrabold text-white font-display tracking-tight">
              INTERACTIVE <span className="text-cyan-400 text-glow-cyan">CODE EXPLORER</span>
            </h2>
          </div>
          <p className="text-slate-400 text-sm max-w-md">
            Inspecting production design patterns, memory pool layouts, and deterministic algorithms engineered for low latency.
          </p>
        </div>

        {/* Code Explorer Interface */}
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
          
          {/* Left Pattern Selector Tabs */}
          <div className="lg:col-span-4 space-y-3 font-mono">
            <span className="text-[10px] text-slate-400 uppercase tracking-widest px-2">DESIGN PATTERNS:</span>
            {CODE_PATTERNS.map((pattern) => {
              const isSelected = pattern.id === selectedPatternId;
              return (
                <button
                  key={pattern.id}
                  onClick={() => setSelectedPatternId(pattern.id)}
                  className={`w-full text-left p-4 rounded-xl border transition-all ${
                    isSelected
                      ? 'bg-[#0c101c] border-cyan-400/60 text-white glow-cyan'
                      : 'bg-[#05070d] border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] bg-cyan-500/10 text-cyan-400 px-2 py-0.5 rounded border border-cyan-500/30 uppercase">
                      {pattern.language}
                    </span>
                    <span className="text-[10px] text-slate-500">{pattern.engine}</span>
                  </div>
                  <p className="text-xs font-bold text-white mt-2">{pattern.title}</p>
                  <p className="text-[10px] text-purple-400 mt-0.5">{pattern.patternName}</p>
                </button>
              );
            })}
          </div>

          {/* Right Code Display & Explanation */}
          <div className="lg:col-span-8 bg-[#0c101c] border border-slate-800 rounded-xl overflow-hidden shadow-2xl flex flex-col justify-between hud-box">
            
            {/* Terminal Header */}
            <div className="bg-[#05070d] px-6 py-4 border-b border-slate-800 flex items-center justify-between font-mono">
              <div className="flex items-center space-x-3">
                <div className="flex space-x-1.5">
                  <div className="w-3 h-3 rounded-full bg-red-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-yellow-500/80"></div>
                  <div className="w-3 h-3 rounded-full bg-emerald-500/80"></div>
                </div>
                <span className="text-xs text-slate-300 font-bold">{activePattern.title}</span>
                <span className="text-[10px] text-slate-500 hidden sm:inline">({activePattern.patternName})</span>
              </div>

              <button
                onClick={handleCopyCode}
                className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-cyan-400 transition-colors bg-[#0c101c] px-3 py-1.5 rounded border border-slate-800 hover:border-cyan-500/40"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'COPIED!' : 'COPY CODE'}</span>
              </button>
            </div>

            {/* Code Body */}
            <div className="p-6 overflow-x-auto font-mono text-xs text-slate-300 leading-relaxed bg-[#06080e] border-b border-slate-800/80 max-h-[420px]">
              <pre className="text-slate-200">
                <code>{activePattern.code}</code>
              </pre>
            </div>

            {/* Architectural Rationale & Breakdown */}
            <div className="p-6 bg-[#0c101c] space-y-4 font-mono">
              <div className="flex items-center space-x-2 text-xs font-bold text-cyan-400">
                <Terminal className="w-4 h-4" />
                <span>ARCHITECTURAL RATIONALE & ADVANTAGES</span>
              </div>

              <p className="text-xs text-slate-300 font-sans leading-relaxed">
                {activePattern.summary}
              </p>

              <div className="space-y-2 pt-1 font-sans">
                {activePattern.architectureBreakdown.map((point, pIdx) => (
                  <div key={pIdx} className="flex items-start space-x-2 text-xs text-slate-300">
                    <span className="text-cyan-400 font-mono font-bold">›</span>
                    <span>{point}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>

        </div>

      </div>
    </section>
  );
};
