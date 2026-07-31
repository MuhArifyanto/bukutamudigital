import React, { useState } from 'react';
import { Cpu, Code, ExternalLink, Shield, Terminal, Zap, ArrowUpRight } from 'lucide-react';
import { PROJECTS } from '../data/portfolioData';
import type { Project, ProjectCategory } from '../types/portfolio';

interface ProjectShowcaseProps {
  onSelectProject: (project: Project) => void;
}

export const ProjectShowcase: React.FC<ProjectShowcaseProps> = ({ onSelectProject }) => {
  const [selectedCategory, setSelectedCategory] = useState<ProjectCategory>('all');

  const filteredProjects = selectedCategory === 'all' 
    ? PROJECTS 
    : PROJECTS.filter(p => p.category === selectedCategory);

  const categories: { id: ProjectCategory; label: string }[] = [
    { id: 'all', label: 'ALL SYSTEMS' },
    { id: 'action-combat', label: 'ACTION COMBAT' },
    { id: 'custom-engine', label: 'CUSTOM ENGINES' },
    { id: 'ai-physics', label: 'AI & PHYSICS' },
    { id: 'shaders-vfx', label: 'SHADERS & VFX' },
  ];

  return (
    <section id="projects" className="py-24 relative bg-[#05070d]">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        
        {/* Section Title */}
        <div className="flex flex-col md:flex-row md:items-end justify-between mb-12 space-y-4 md:space-y-0">
          <div className="space-y-3">
            <div className="inline-flex items-center space-x-2 px-3 py-1 bg-purple-500/10 border border-purple-500/30 rounded-full text-xs font-mono text-purple-400">
              <Cpu className="w-3.5 h-3.5" />
              <span>PRODUCTION SHOWCASE</span>
            </div>
            <h2 className="text-3xl sm:text-5xl font-extrabold text-white font-display tracking-tight">
              FEATURED GAME <span className="text-purple-400 text-glow-purple">SYSTEMS & ENGINES</span>
            </h2>
          </div>

          <p className="text-slate-400 text-sm max-w-md">
            Production-grade gameplay systems, custom engine subsystems, AI behavior frameworks, and shader pipelines.
          </p>
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap gap-2 mb-10 font-mono text-xs">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-4 py-2 rounded-lg border transition-all ${
                selectedCategory === cat.id
                  ? 'bg-purple-500/20 text-purple-300 border-purple-400 font-bold glow-purple'
                  : 'bg-[#0c101c] text-slate-400 border-slate-800 hover:border-slate-700 hover:text-slate-200'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Project Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {filteredProjects.map((project) => (
            <div
              key={project.id}
              className="bg-[#0c101c] border border-slate-800 hover:border-purple-500/50 rounded-xl overflow-hidden transition-all duration-300 hover:-translate-y-1 group flex flex-col justify-between hud-box"
            >
              <div>
                {/* Image Banner Container */}
                <div className="relative h-56 overflow-hidden bg-slate-900">
                  <img
                    src={project.bannerImage}
                    alt={project.title}
                    className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-500 opacity-80 group-hover:opacity-100"
                  />
                  <div className="absolute inset-0 bg-gradient-to-t from-[#0c101c] via-[#0c101c]/40 to-transparent"></div>

                  {/* Engine Tag */}
                  <div className="absolute top-4 left-4 font-mono text-[10px] bg-[#06080e]/90 text-cyan-400 px-3 py-1 rounded border border-cyan-500/30 backdrop-blur">
                    {project.engine}
                  </div>

                  {/* Role Badge */}
                  <div className="absolute top-4 right-4 font-mono text-[10px] bg-purple-500/20 text-purple-300 px-3 py-1 rounded border border-purple-500/40 backdrop-blur">
                    {project.role}
                  </div>

                  {/* Overlay Title */}
                  <div className="absolute bottom-4 left-4 right-4">
                    <h3 className="text-xl font-extrabold text-white font-display tracking-wide group-hover:text-cyan-400 transition-colors">
                      {project.title}
                    </h3>
                    <p className="text-xs text-slate-300 font-mono mt-0.5">{project.subtitle}</p>
                  </div>
                </div>

                {/* Card Body */}
                <div className="p-6 space-y-6">
                  
                  {/* Summary */}
                  <p className="text-slate-300 text-sm leading-relaxed">
                    {project.summary}
                  </p>

                  {/* Key Metrics Grid */}
                  <div className="grid grid-cols-3 gap-2 font-mono bg-[#05070d] p-3 rounded-lg border border-slate-800">
                    {project.metrics.map((m, idx) => (
                      <div key={idx} className="text-center">
                        <p className="text-[10px] text-slate-400">{m.label}</p>
                        <p className="text-xs font-bold text-cyan-400 mt-0.5">{m.value}</p>
                      </div>
                    ))}
                  </div>

                  {/* Architecture Highlights Pill */}
                  <div className="space-y-2 font-mono">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider">Key System Features:</span>
                    <div className="flex flex-wrap gap-1.5 text-[11px]">
                      {project.tags.map((tag, idx) => (
                        <span key={idx} className="px-2 py-0.5 bg-[#05070d] text-slate-300 border border-slate-800 rounded">
                          {tag}
                        </span>
                      ))}
                    </div>
                  </div>

                </div>
              </div>

              {/* Card Footer Button */}
              <div className="p-6 pt-0">
                <button
                  onClick={() => onSelectProject(project)}
                  className="w-full py-3 bg-gradient-to-r from-purple-950 to-slate-900 hover:from-purple-900 hover:to-slate-800 text-purple-300 hover:text-white font-mono text-xs font-bold rounded border border-purple-500/40 transition-all flex items-center justify-center space-x-2 group-hover:border-purple-400 glow-purple"
                >
                  <Code className="w-4 h-4 text-purple-400" />
                  <span>INSPECT_ARCHITECTURE_&_CODE</span>
                  <ArrowUpRight className="w-4 h-4 text-purple-400 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition-transform" />
                </button>
              </div>

            </div>
          ))}
        </div>

      </div>
    </section>
  );
};
