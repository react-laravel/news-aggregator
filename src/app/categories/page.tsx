import { BottomNav } from "@/components/site/bottom-nav";
import { CategoryPreferences } from "@/components/site/category-preferences";

export default function CategoriesPage() {
  return (
    <main className="min-h-screen bg-zinc-50 pb-24">
      <div className="mx-auto max-w-2xl px-4 py-6">
        <CategoryPreferences />
      </div>
      <BottomNav />
    </main>
  );
}

