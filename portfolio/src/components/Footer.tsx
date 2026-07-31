import React from 'react';
import { Terminal, Shield, Cpu, Heart } from 'lucide-react';

export const Footer: React.FC = () => {
  return (
    <footer className="bg-[#05070d] border-t border-slate-800/80 py-12 font-mono text-xs text-slate-400">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 space-y-6">
        
        <div className="flex flex-col md:flex-row items-center justify-between gap-4 border-b border-slate-800/60 pb-6">
          
          <div className="flex items-center space-x-3">
            <div className="w-8 h-8 bg-[#0c101c] border border-cyan-500/40 rounded flex items-center justify-center text-cyan-400 font-bold">
              VX
            </div>
            <div>
              <p className="font-bold text-white tracking-wider">VANGUARD<span className="text-cyan-400">_SYSTEMS</span></p>
              <p className="text-[10px] text-slate-400">Lead Gameplay & Combat Architecture</p>
            </div>
          </div>

          <div className="flex space-x-6 text-[11px] text-slate-400">
            <a href="#hero" className="hover:text-cyan-400 transition-colors">HOME</a>
            <a href="#combat-engine" className="hover:text-cyan-400 transition-colors">COMBAT ENGINE</a>
            <a href="#projects" className="hover:text-cyan-400 transition-colors">PROJECTS</a>
            <a href="#architecture" className="hover:text-cyan-400 transition-colors">STACK</a>
            <a href="#code-sandbox" className="hover:text-cyan-400 transition-colors">PATTERNS</a>
          </div>

        </div>

        <div className="flex flex-col sm:flex-row items-center justify-between text-[10px] text-slate-400 gap-2">
          <p>© {new Date().getFullYear()} VANGUARD GAME SYSTEMS PORTFOLIO. ALL RIGHTS RESERVED.</p>
          <div className="flex items-center space-x-2">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
            <span>SYSTEMS_OPERATIONAL // 120 FPS DETERMINISTIC TICK</span>
          </div>
        </div>

      </div>
    </footer>
  );
};
