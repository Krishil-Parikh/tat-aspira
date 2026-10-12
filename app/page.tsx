"use client";

import { ScrollProgress } from '../components/ScrollProgress';
import { Navbar } from '../components/Navbar';
import { Hero } from '../components/Hero';
import { Stats } from '../components/Stats';
import { HowItWorks } from '../components/HowItWorks';
import { Features } from '../components/Features';
import { Preview } from '../components/Preview';
import { Testimonials } from '../components/Testimonials';
import { Team } from '../components/Team';
import { Contact } from '../components/Contact';
import { FooterCTA } from '../components/FooterCTA';

export default function HomePage() {
  return (
    <div className="min-h-screen bg-[#F8FAFC] text-[#0F172A] overflow-x-hidden">

      <ScrollProgress />
      <Navbar />
      <main>
        <Hero />
        <Stats />
        <HowItWorks />
        <Features />
        <Preview />
        <Testimonials />
        <Team />
        <Contact />
        <FooterCTA />
      </main>
    </div>
  );
}
