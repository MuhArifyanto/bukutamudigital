import React, { useState } from 'react';
import { Navbar } from './components/Navbar';
import { Hero } from './components/Hero';
import { CombatVisualizer } from './components/CombatVisualizer';
import { ProjectShowcase } from './components/ProjectShowcase';
import { ArchitectureSection } from './components/ArchitectureSection';
import { CodeSandbox } from './components/CodeSandbox';
import { ContactSection } from './components/ContactSection';
import { Footer } from './components/Footer';
import { ProjectModal } from './components/ProjectModal';
import type { Project } from './types/portfolio';

export function App() {
  const [activeSection, setActiveSection] = useState('hero');
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);

  const scrollToSection = (id: string) => {
    setActiveSection(id);
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <div className="min-h-screen bg-[#05070d] text-slate-200 selection:bg-cyan-500 selection:text-slate-950">
      {/* Navigation Header */}
      <Navbar activeSection={activeSection} setActiveSection={setActiveSection} />

      {/* Hero Section */}
      <Hero
        onExploreCombatClick={() => scrollToSection('combat-engine')}
        onExploreProjectsClick={() => scrollToSection('projects')}
      />

      {/* Interactive Combat Engine & State Machine Simulator */}
      <CombatVisualizer />

      {/* Projects Catalog */}
      <ProjectShowcase onSelectProject={(p) => setSelectedProject(p)} />

      {/* Architecture & Tech Matrix */}
      <ArchitectureSection />

      {/* Code Pattern Explorer */}
      <CodeSandbox />

      {/* Terminal Contact Section */}
      <ContactSection />

      {/* Footer */}
      <Footer />

      {/* Project Architectural Deep Dive Modal */}
      <ProjectModal
        project={selectedProject}
        onClose={() => setSelectedProject(null)}
      />
    </div>
  );
}

export default App;
