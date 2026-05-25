import { Hero } from "@/components/Hero";
import { Features } from "@/components/Features";
import { TechStack } from "@/components/TechStack";
import { QuickStart } from "@/components/QuickStart";
import { Footer } from "@/components/Footer";

export default function App() {
  return (
    <div className="min-h-screen bg-slate-900">
      <Hero />
      <Features />
      <TechStack />
      <QuickStart />
      <Footer />
    </div>
  );
}
