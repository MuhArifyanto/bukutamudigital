import React, { useState, useEffect } from 'react';
import { Shield, Zap, RefreshCw, Terminal, Layers, Crosshair, Play, CheckCircle2 } from 'lucide-react';
import { COMBO_STATES } from '../data/portfolioData';
import type { ComboStateNode } from '../types/portfolio';

export const CombatVisualizer: React.FC = () => {
  const [currentStateKey, setCurrentStateKey] = useState<string>('idle');
  const [inputLog, setInputLog] = useState<{ time: string; text: string; type: 'light' | 'heavy' | 'parry' | 'dodge' | 'reset' }[]>([]);
  const [currentTab, setCurrentTab] = useState<'simulator' | 'buffer' | 'sweeps'>('simulator');
  const [totalDamage, setTotalDamage] = useState<number>(0);
  const [staggerGauge, setStaggerGauge] = useState<number>(0);
  const [isHitActive, setIsHitActive] = useState<boolean>(false);

  const currentState: ComboStateNode = COMBO_STATES[currentStateKey] || COMBO_STATES.idle;

  // Keyboard shortcut listener for J, K, L, Space
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (['INPUT', 'TEXTAREA'].includes((e.target as HTMLElement).tagName)) return;

      const key = e.key.toLowerCase();
      if (key === 'j') handleTriggerInput('light');
      else if (key === 'k') handleTriggerInput('heavy');
      else if (key === 'l') handleTriggerInput('parry');
      else if (key === ' ') {
        e.preventDefault();
        handleTriggerInput('dodge');
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentStateKey]);

  const logInput = (text: string, type: 'light' | 'heavy' | 'parry' | 'dodge' | 'reset') => {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false, minute: '2-digit', second: '2-digit' }) + '.' + Math.floor(Math.random() * 90 + 10);
    setInputLog((prev) => [{ time, text, type }, ...prev.slice(0, 7)]);
  };

  const handleTriggerInput = (action: 'light' | 'heavy' | 'parry' | 'dodge') => {
    let nextKey = 'idle';

    if (action === 'light') {
      if (currentStateKey === 'idle') nextKey = 'light_1';
      else if (currentStateKey === 'light_1') nextKey = 'light_2';
      else if (currentStateKey === 'dodge_cancel') nextKey = 'light_1';
      else nextKey = 'light_1';
      logInput(`EXECUTED [J]: ${COMBO_STATES[nextKey]?.name || 'LIGHT_ATTACK'}`, 'light');
    } else if (action === 'heavy') {
      if (['light_1', 'light_2'].includes(currentStateKey)) nextKey = 'heavy_finisher';
      else nextKey = 'heavy_finisher';
      logInput(`EXECUTED [K]: ${COMBO_STATES[nextKey]?.name || 'HEAVY_FINISHER'}`, 'heavy');
    } else if (action === 'parry') {
      nextKey = 'parry';
      logInput('EXECUTED [L]: DEFENSIVE_PARRY', 'parry');
    } else if (action === 'dodge') {
      nextKey = 'dodge_cancel';
      logInput('EXECUTED [SPACE]: PHASE_SHIFT_DODGE', 'dodge');
    }

    const targetNode = COMBO_STATES[nextKey] || COMBO_STATES.idle;
    setCurrentStateKey(nextKey);

    if (targetNode.damage > 0) {
      setTotalDamage((prev) => prev + targetNode.damage);
      setIsHitActive(true);
      setTimeout(() => setIsHitActive(false), 300);
    }

    if (targetNode.poiseDamage > 0) {
      setStaggerGauge((prev) => {
        const nextStagger = prev + targetNode.poiseDamage;
        if (nextStagger >= 300) {
          setTimeout(() => setStaggerGauge(0), 1000);
          return 300;
        }
        return nextStagger;
      });
    }
  };

  const handleReset = () => {
    setCurrentStateKey('idle');
    setTotalDamage(0);
    setStaggerGauge(0);
    logInput('RESET COMBAT STATE TO NEUTRAL_IDLE', 'reset');
  };

  return (
    <section id="combat-engine" className="py-20 relative bg-[#06080e] border-t border-b border-cyan-500/20">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Header */}
        <div className="text-center space-y-4 mb-14">
          <div className="inline-flex items-center space-x-2 px-3 py-1 bg-cyan-500/10 border border-cyan-500/30 rounded-full text-xs font-mono text-cyan-400">
            <Zap className="w-3.5 h-3.5" />
            <span>INTERACTIVE MECHANICS PREVIEW</span>
          </div>
          <h2 className="text-3xl sm:text-5xl font-extrabold text-white font-display tracking-tight">
            FRAME-ACCURATE <span className="text-cyan-400 text-glow-cyan">COMBAT ENGINE</span> VISUALIZER
          </h2>
          <p className="text-slate-400 max-w-2xl mx-auto text-sm sm:text-base">
            Test and inspect the deterministic state machine, cancel windows, and frame data execution. Press hotkeys <kbd className="px-1.5 py-0.5 bg-slate-800 text-cyan-400 rounded border border-slate-700">J</kbd>, <kbd className="px-1.5 py-0.5 bg-slate-800 text-cyan-400 rounded border border-slate-700">K</kbd>, <kbd className="px-1.5 py-0.5 bg-slate-800 text-cyan-400 rounded border border-slate-700">L</kbd>, <kbd className="px-1.5 py-0.5 bg-slate-800 text-cyan-400 rounded border border-slate-700">Space</kbd> or click the buttons below.
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex justify-center mb-8">
          <div className="bg-[#0c101c] p-1 rounded-lg border border-slate-800 flex space-x-2 font-mono text-xs">
            <button
              onClick={() => setCurrentTab('simulator')}
              className={`px-4 py-2 rounded transition-all ${
                currentTab === 'simulator' ? 'bg-cyan-500 text-slate-950 font-bold glow-cyan' : 'text-slate-400 hover:text-white'
              }`}
            >
              STATE MACHINE SIMULATOR
            </button>
            <button
              onClick={() => setCurrentTab('buffer')}
              className={`px-4 py-2 rounded transition-all ${
                currentTab === 'buffer' ? 'bg-cyan-500 text-slate-950 font-bold glow-cyan' : 'text-slate-400 hover:text-white'
              }`}
            >
              INPUT BUFFER QUEUE
            </button>
            <button
              onClick={() => setCurrentTab('sweeps')}
              className={`px-4 py-2 rounded transition-all ${
                currentTab === 'sweeps' ? 'bg-cyan-500 text-slate-950 font-bold glow-cyan' : 'text-slate-400 hover:text-white'
              }`}
            >
              HITBOX SWEEP PIPELINE
            </button>
          </div>
        </div>

        {/* Tab 1: State Machine Simulator */}
        {currentTab === 'simulator' && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8">
            
            {/* Left: Input Controller & Frame Data Display */}
            <div className="lg:col-span-5 space-y-6">
              
              {/* Interactive Controller Box */}
              <div className="bg-[#0c101c] border border-cyan-500/30 rounded-xl p-6 glow-cyan space-y-5">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-mono">
                  <span className="text-xs text-cyan-400 font-bold flex items-center gap-2">
                    <Crosshair className="w-4 h-4" /> INPUT COMMAND CONTROLLER
                  </span>
                  <button
                    onClick={handleReset}
                    className="text-[11px] text-slate-400 hover:text-yellow-400 flex items-center gap-1 transition-colors"
                  >
                    <RefreshCw className="w-3 h-3" /> RESET
                  </button>
                </div>

                {/* Input Buttons */}
                <div className="grid grid-cols-2 gap-3 font-mono">
                  <button
                    onClick={() => handleTriggerInput('light')}
                    className="p-3 bg-gradient-to-r from-cyan-950 to-cyan-900 hover:from-cyan-900 hover:to-cyan-800 border border-cyan-500/50 rounded-lg text-left transition-all active:scale-95 group"
                  >
                    <div className="text-[10px] text-cyan-400 flex justify-between">
                      <span>KEY: [J]</span>
                      <span className="group-hover:translate-x-1 transition-transform">→</span>
                    </div>
                    <div className="text-xs font-bold text-white mt-1">LIGHT ATTACK</div>
                    <div className="text-[10px] text-slate-400">Quick slash (4f startup)</div>
                  </button>

                  <button
                    onClick={() => handleTriggerInput('heavy')}
                    className="p-3 bg-gradient-to-r from-purple-950 to-purple-900 hover:from-purple-900 hover:to-purple-800 border border-purple-500/50 rounded-lg text-left transition-all active:scale-95 group"
                  >
                    <div className="text-[10px] text-purple-400 flex justify-between">
                      <span>KEY: [K]</span>
                      <span className="group-hover:translate-x-1 transition-transform">→</span>
                    </div>
                    <div className="text-xs font-bold text-white mt-1">HEAVY FINISHER</div>
                    <div className="text-[10px] text-slate-400">Cleave (12f startup)</div>
                  </button>

                  <button
                    onClick={() => handleTriggerInput('parry')}
                    className="p-3 bg-gradient-to-r from-emerald-950 to-emerald-900 hover:from-emerald-900 hover:to-emerald-800 border border-emerald-500/50 rounded-lg text-left transition-all active:scale-95 group"
                  >
                    <div className="text-[10px] text-emerald-400 flex justify-between">
                      <span>KEY: [L]</span>
                      <span className="group-hover:translate-x-1 transition-transform">→</span>
                    </div>
                    <div className="text-xs font-bold text-white mt-1">DEFENSIVE PARRY</div>
                    <div className="text-[10px] text-slate-400">Frame 2 active block</div>
                  </button>

                  <button
                    onClick={() => handleTriggerInput('dodge')}
                    className="p-3 bg-gradient-to-r from-yellow-950 to-yellow-900 hover:from-yellow-900 hover:to-yellow-800 border border-yellow-500/50 rounded-lg text-left transition-all active:scale-95 group"
                  >
                    <div className="text-[10px] text-yellow-400 flex justify-between">
                      <span>KEY: [SPACE]</span>
                      <span className="group-hover:translate-x-1 transition-transform">→</span>
                    </div>
                    <div className="text-xs font-bold text-white mt-1">PHASE DODGE</div>
                    <div className="text-[10px] text-slate-400">i-Frame cancel dash</div>
                  </button>
                </div>

                {/* Keyboard Helper */}
                <p className="text-[11px] text-slate-400 text-center font-mono">
                  💡 Keyboard Hotkeys Active: <span className="text-cyan-400">J</span> (Light), <span className="text-purple-400">K</span> (Heavy), <span className="text-emerald-400">L</span> (Parry), <span className="text-yellow-400">Space</span> (Dodge)
                </p>
              </div>

              {/* Damage & Poise Telemetry */}
              <div className="bg-[#0c101c] border border-slate-800 rounded-xl p-5 space-y-4 font-mono">
                <div className="text-xs font-bold text-slate-200 flex justify-between items-center">
                  <span>DAMAGE & STAGGER TELEMETRY</span>
                  {isHitActive && <span className="text-red-400 text-[10px] animate-ping">HIT_IMPACT!</span>}
                </div>

                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-[#05070d] p-3 rounded border border-slate-800">
                    <p className="text-[10px] text-slate-400">CUMULATIVE DAMAGE</p>
                    <p className="text-2xl font-extrabold text-cyan-400">{totalDamage} <span className="text-xs font-normal text-slate-400">DMG</span></p>
                  </div>
                  <div className="bg-[#05070d] p-3 rounded border border-slate-800">
                    <p className="text-[10px] text-slate-400">ENEMY POISE STAGGER</p>
                    <p className="text-2xl font-extrabold text-yellow-400">{staggerGauge} / 300</p>
                  </div>
                </div>

                {/* Stagger Gauge Bar */}
                <div className="space-y-1">
                  <div className="flex justify-between text-[10px] text-slate-400">
                    <span>POISE THRESHOLD</span>
                    <span>{staggerGauge >= 300 ? 'GUARD BROKEN!' : `${Math.round((staggerGauge / 300) * 100)}%`}</span>
                  </div>
                  <div className="w-full bg-slate-900 h-2.5 rounded-full overflow-hidden border border-slate-800">
                    <div 
                      className={`h-full transition-all duration-300 ${staggerGauge >= 300 ? 'bg-red-500 animate-pulse' : 'bg-gradient-to-r from-yellow-500 to-red-500'}`}
                      style={{ width: `${Math.min(100, (staggerGauge / 300) * 100)}%` }}
                    ></div>
                  </div>
                </div>
              </div>

            </div>

            {/* Right: State Flowchart & Active Node Breakdown */}
            <div className="lg:col-span-7 space-y-6">
              
              {/* Active State Banner */}
              <div className="bg-[#0c101c] border border-cyan-500/40 rounded-xl p-6 space-y-4">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3 font-mono">
                  <div>
                    <span className="text-[10px] text-slate-400">CURRENT_STATE_NODE</span>
                    <h3 className="text-xl font-extrabold text-cyan-400 font-display">{currentState.name}</h3>
                  </div>
                  <span className="text-xs font-mono px-3 py-1 bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 rounded">
                    TRIGGER: {currentState.inputTrigger}
                  </span>
                </div>

                <p className="text-slate-300 text-sm">{currentState.description}</p>

                {/* Frame Data Breakdown Bar */}
                <div className="space-y-2 pt-2">
                  <div className="flex justify-between text-xs font-mono text-slate-300">
                    <span>FRAME DATA BREAKDOWN (60 FPS)</span>
                    <span className="text-cyan-400">Total Duration: {currentState.startupFrames + currentState.activeFrames + currentState.recoveryFrames} frames</span>
                  </div>

                  <div className="flex rounded overflow-hidden text-[10px] font-mono text-center font-bold h-7 border border-slate-800">
                    {currentState.startupFrames > 0 && (
                      <div 
                        className="bg-yellow-500/30 text-yellow-300 flex items-center justify-center border-r border-slate-800" 
                        style={{ flex: currentState.startupFrames }}
                      >
                        Startup ({currentState.startupFrames}f)
                      </div>
                    )}
                    {currentState.activeFrames > 0 && (
                      <div 
                        className="bg-cyan-500/40 text-cyan-200 flex items-center justify-center border-r border-slate-800 animate-pulse" 
                        style={{ flex: currentState.activeFrames }}
                      >
                        Active ({currentState.activeFrames}f)
                      </div>
                    )}
                    {currentState.recoveryFrames > 0 && (
                      <div 
                        className="bg-purple-500/30 text-purple-300 flex items-center justify-center" 
                        style={{ flex: currentState.recoveryFrames }}
                      >
                        Recovery ({currentState.recoveryFrames}f)
                      </div>
                    )}
                  </div>

                  <div className="grid grid-cols-4 gap-2 text-[10px] font-mono text-center text-slate-400 pt-1">
                    <div>Damage: <span className="text-white font-bold">{currentState.damage}</span></div>
                    <div>Poise Dmg: <span className="text-white font-bold">{currentState.poiseDamage}</span></div>
                    <div>Cancel Window: <span className="text-cyan-400 font-bold">Frame {currentState.cancelWindowStartFrame}+</span></div>
                    <div>Type: <span className="text-purple-400 font-bold">{currentState.hitType}</span></div>
                  </div>
                </div>
              </div>

              {/* State Machine Nodes Flow Graph */}
              <div className="bg-[#0c101c] border border-slate-800 rounded-xl p-6 space-y-4 font-mono">
                <div className="text-xs font-bold text-slate-200 flex items-center space-x-2">
                  <Layers className="w-4 h-4 text-cyan-400" />
                  <span>COMBO STATE NODE GRAPH</span>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                  {Object.values(COMBO_STATES).map((node) => {
                    const isCurrent = node.id === currentStateKey;
                    return (
                      <div
                        key={node.id}
                        onClick={() => {
                          setCurrentStateKey(node.id);
                          logInput(`SELECTED NODE: ${node.name}`, 'light');
                        }}
                        className={`p-3 rounded-lg border text-left cursor-pointer transition-all ${
                          isCurrent
                            ? 'bg-cyan-500/20 border-cyan-400 text-cyan-300 glow-cyan font-bold scale-105'
                            : 'bg-[#05070d] border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-200'
                        }`}
                      >
                        <div className="flex justify-between items-center">
                          <span className="text-[10px] text-slate-400">{node.id}</span>
                          {isCurrent && <CheckCircle2 className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />}
                        </div>
                        <p className="text-xs mt-1 truncate">{node.name}</p>
                      </div>
                    );
                  })}
                </div>
              </div>

              {/* Terminal Log Console */}
              <div className="bg-[#05070d] border border-slate-800 rounded-xl p-4 font-mono text-xs space-y-2">
                <div className="flex items-center space-x-2 text-slate-400 border-b border-slate-800 pb-2">
                  <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="text-[11px]">LIVE_INPUT_LOG_STREAM</span>
                </div>
                <div className="space-y-1.5 max-h-32 overflow-y-auto">
                  {inputLog.length === 0 ? (
                    <p className="text-slate-600 italic">No input commands executed yet. Press J, K, L or Space.</p>
                  ) : (
                    inputLog.map((log, idx) => (
                      <div key={idx} className="flex justify-between text-[11px]">
                        <span className="text-slate-500">[{log.time}]</span>
                        <span className={
                          log.type === 'light' ? 'text-cyan-400' :
                          log.type === 'heavy' ? 'text-purple-400' :
                          log.type === 'parry' ? 'text-emerald-400' :
                          log.type === 'dodge' ? 'text-yellow-400' : 'text-slate-400'
                        }>
                          {log.text}
                        </span>
                      </div>
                    ))
                  )}
                </div>
              </div>

            </div>

          </div>
        )}

        {/* Tab 2: Input Buffer Queue Architecture */}
        {currentTab === 'buffer' && (
          <div className="bg-[#0c101c] border border-slate-800 rounded-xl p-8 space-y-6 font-mono">
            <div className="space-y-2">
              <h3 className="text-xl font-bold text-cyan-400 font-display">DETERMINISTIC INPUT BUFFER QUEUE</h3>
              <p className="text-slate-300 text-sm font-sans max-w-3xl">
                In competitive action games, pressing a button 50ms before an animation completes must not drop the input. My custom input queue captures key events into a 16.6ms frame-stamped ring buffer.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-6 pt-4">
              <div className="bg-[#05070d] p-5 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs text-cyan-400 font-bold">1. CAPTURE & STAMP</span>
                <p className="text-xs text-slate-300 font-sans">
                  Inputs are stamped with precise High-Resolution Timestamps (<code className="text-cyan-300">std::chrono::high_resolution_clock</code>).
                </p>
              </div>
              <div className="bg-[#05070d] p-5 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs text-purple-400 font-bold">2. CANCEL EVALUATION</span>
                <p className="text-xs text-slate-300 font-sans">
                  When current state reaches <code className="text-purple-300">CancelWindowStartFrame</code>, buffer is queried for valid priority overrides.
                </p>
              </div>
              <div className="bg-[#05070d] p-5 rounded-lg border border-slate-800 space-y-2">
                <span className="text-xs text-yellow-400 font-bold">3. ZERO DROPPED FRAMES</span>
                <p className="text-xs text-slate-300 font-sans">
                  Guarantees frame-perfect execution without player feeling sluggishness or unresponsive controls.
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Hitbox Sweep Pipeline */}
        {currentTab === 'sweeps' && (
          <div className="bg-[#0c101c] border border-slate-800 rounded-xl p-8 space-y-6 font-mono">
            <div className="space-y-2">
              <h3 className="text-xl font-bold text-cyan-400 font-display">CONTINUOUS SWEEP COLLISION PIPELINE</h3>
              <p className="text-slate-300 text-sm font-sans max-w-3xl">
                Traditional collision triggers often fail at 60+ FPS when sword blades travel several meters in a single frame. My socket trajectory sweep algorithm interpolates capsule volumes between consecutive ticks.
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6 pt-4 font-sans text-xs text-slate-300">
              <div className="bg-[#05070d] p-5 rounded-lg border border-slate-800 space-y-3">
                <span className="text-cyan-400 font-mono font-bold text-sm">❌ Standard Overlap Trigger (Flawed)</span>
                <p>Checks position only at frame tick. Fast swinging blades skip over targets between frames, causing missed hits.</p>
              </div>
              <div className="bg-[#05070d] p-5 rounded-lg border border-cyan-500/40 space-y-3 glow-cyan">
                <span className="text-emerald-400 font-mono font-bold text-sm">✅ Socket Trajectory Sweep (Implemented)</span>
                <p>Calculates the motion vector between Socket_Base and Socket_Tip across Frame (N-1) and Frame N, performing an airtight capsule sweep.</p>
              </div>
            </div>
          </div>
        )}

      </div>
    </section>
  );
};
