import React, { useState } from 'react';
import { X, Code, CheckCircle2, Copy, Check, Cpu, Layers } from 'lucide-react';
import type { Project } from '../types/portfolio';

interface ProjectModalProps {
  project: Project | null;
  onClose: () => void;
}

export const ProjectModal: React.FC<ProjectModalProps> = ({ project, onClose }) => {
  const [copied, setCopied] = useState(false);

  if (!project) return null;

  const handleCopy = () => {
    navigator.clipboard.writeText(project.codeSnippet.code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 lg:p-8 bg-[#05070d]/90 backdrop-blur-md overflow-y-auto animate-fade-in">
      <div 
        className="relative w-full max-w-4xl bg-[#0c101c] border border-cyan-500/40 rounded-2xl overflow-hidden shadow-[0_0_50px_rgba(0,240,255,0.2)] hud-box space-y-6 my-auto"
        onClick={(e) => e.stopPropagation()}
      >
        
        {/* Banner Image & Close Button */}
        <div className="relative h-64 sm:h-80 overflow-hidden bg-slate-900">
          <img
            src={project.bannerImage}
            alt={project.title}
            className="w-full h-full object-cover opacity-85"
          />
          <div className="absolute inset-0 bg-gradient-to-t from-[#0c101c] via-[#0c101c]/50 to-transparent"></div>

          {/* Close Modal Button */}
          <button
            onClick={onClose}
            className="absolute top-4 right-4 p-2 bg-[#06080e]/80 hover:bg-red-500/20 text-slate-400 hover:text-red-400 border border-slate-700 hover:border-red-500/40 rounded-full transition-colors backdrop-blur"
          >
            <X className="w-5 h-5" />
          </button>

          {/* Banner Details */}
          <div className="absolute bottom-6 left-6 right-6 space-y-2">
            <div className="flex flex-wrap gap-2 font-mono text-[10px]">
              <span className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 px-2.5 py-1 rounded backdrop-blur">
                {project.engine}
              </span>
              <span className="bg-purple-500/20 text-purple-300 border border-purple-500/40 px-2.5 py-1 rounded backdrop-blur">
                {project.role}
              </span>
              <span className="bg-slate-800 text-slate-300 border border-slate-700 px-2.5 py-1 rounded backdrop-blur">
                Year {project.year}
              </span>
            </div>

            <h2 className="text-2xl sm:text-4xl font-extrabold text-white font-display">
              {project.title}
            </h2>
            <p className="text-sm font-mono text-cyan-400">{project.subtitle}</p>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-6 sm:p-8 space-y-8 max-h-[60vh] overflow-y-auto font-sans">
          
          {/* Detailed Description */}
          <div className="space-y-2">
            <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-widest">SYSTEM OVERVIEW</h4>
            <p className="text-slate-300 text-sm leading-relaxed">{project.detailedDescription}</p>
          </div>

          {/* Performance Metrics Grid */}
          <div className="space-y-3 font-mono">
            <h4 className="text-xs font-bold text-purple-400 uppercase tracking-widest">BENCHMARKS & METRICS</h4>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {project.metrics.map((metric, idx) => (
                <div key={idx} className="bg-[#05070d] p-4 rounded-lg border border-slate-800">
                  <p className="text-[10px] text-slate-400">{metric.label}</p>
                  <p className="text-xl font-bold text-cyan-400 mt-1">{metric.value}</p>
                  <p className="text-[10px] text-slate-500 mt-0.5">{metric.subtext}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Key Features List */}
          <div className="space-y-3">
            <h4 className="text-xs font-mono font-bold text-yellow-400 uppercase tracking-widest">TECHNICAL SPECIFICATIONS</h4>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs text-slate-300">
              {project.features.map((feat, idx) => (
                <div key={idx} className="flex items-start space-x-2 bg-[#05070d] p-3 rounded border border-slate-800/80">
                  <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0 mt-0.5" />
                  <span>{feat}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Architecture Highlights */}
          <div className="space-y-3">
            <h4 className="text-xs font-mono font-bold text-cyan-400 uppercase tracking-widest">ARCHITECTURE HIGHLIGHTS</h4>
            <div className="space-y-3">
              {project.architectureHighlights.map((arch, idx) => (
                <div key={idx} className="bg-[#05070d] p-4 rounded-lg border border-slate-800 space-y-1">
                  <p className="text-xs font-bold font-mono text-white">{arch.title}</p>
                  <p className="text-xs text-slate-300 leading-relaxed">{arch.description}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Code Snippet Preview */}
          <div className="space-y-3 font-mono">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-cyan-400 uppercase tracking-widest flex items-center gap-2">
                <Code className="w-4 h-4" /> {project.codeSnippet.title}
              </h4>
              <button
                onClick={handleCopy}
                className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-cyan-400 transition-colors bg-[#05070d] px-3 py-1 rounded border border-slate-800"
              >
                {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copied ? 'COPIED!' : 'COPY CODE'}</span>
              </button>
            </div>

            <p className="text-xs font-sans text-slate-400">{project.codeSnippet.description}</p>

            <div className="bg-[#05070d] p-4 rounded-lg border border-slate-800 overflow-x-auto text-xs text-slate-200">
              <pre>
                <code>{project.codeSnippet.code}</code>
              </pre>
            </div>
          </div>

        </div>

        {/* Modal Footer */}
        <div className="p-6 bg-[#05070d] border-t border-slate-800 flex justify-between items-center font-mono text-xs">
          <div className="flex space-x-2">
            {project.tags.map((t, idx) => (
              <span key={idx} className="text-[10px] text-slate-400 bg-slate-900 px-2 py-0.5 rounded">
                #{t}
              </span>
            ))}
          </div>
          <button
            onClick={onClose}
            className="px-5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 rounded transition-colors"
          >
            CLOSE_SPECS
          </button>
        </div>

      </div>
    </div>
  );
};
