export type Unit = 'g' | 'mL'
export type Preference = 'balanced' | 'energy' | 'protein' | 'similarity'
export type Distance = 'varied' | 'related' | 'close'
export type Nutrients = { energy_kcal: string | null; protein_g: string | null; fat_g: string | null; carbohydrate_g: string | null }
export type Food = {
  id: string; name: string; company: string | null; category: string | null;
  basis_amount: string; basis_unit: Unit; nutrients: Nutrients; source_weight: string | null; recommendation_eligible: boolean;
  source: { snapshot_id: string; food_code: string; provider: string; reference_date: string; production_date: string | null; url: string }
}
export type Portion = { amount: string; unit: Unit }
export type Nutrition = { food: Food; portion: Portion; nutrients: Nutrients; missing_nutrients: string[] }
export type Search = { query: string; total: number; requires_confirmation: boolean; items: Food[]; source_total?: number; groups?: { name: string; company: string | null; selected: Food; variants: Food[] }[] }
export type Alternative = { nutrition: Nutrition; reason: string; score: string; energy_difference_kcal: string; protein_difference_g: string; preference_note?: string | null }
export type Recommendation = {
  recommendation_id: string | null; created_at: string | null; original: Nutrition; preference: Preference; distance: Distance;
  next_distance: Distance | null; comparison_note: string; items: Alternative[]; message: string;
  selection_method: 'rules' | 'local_model'; fallback_reason: string | null
  personalization_note?: string | null
}
export type User = { id: string; username: string }
export type Choice = { id: string; client_record_id: string; recommendation_id: string; selected_at: string; nutrition: Nutrition; reason: string }
export type History = { items: Choice[]; total: number; recommendation_count_7_days: number }
export type Profile = { height_cm: string | null; weight_kg: string | null; bmi: string | null }
export type BrowserRecords = { version: 1; recommendations: { id: string; created_at: string }[]; choices: Choice[]; profile: Profile }

export type PersonalSettings = { goal: Preference; favorite_foods: string[]; avoided_foods: string[]; frequent_foods: string[]; energy_target?: string | null; meal_count?: 2 | 3 | 4; default_constraints?: Record<string, import('./plannerTypes').MealConstraints> }
export type Rating = 'like' | 'neutral' | 'dislike'
export type FeedbackReason = 'taste' | 'purpose' | 'unavailable' | 'portion' | 'variety'
export type Feedback = { id: string; phase: 'recommendation' | 'consumed'; context_id: string; food_id: string | null; rating: Rating; reason: FeedbackReason | null; updated_at: string }
export type Meal = { id: string; name: string; food_id: string | null; portion: Portion | null; eaten_at: string; notes: string; nutrients: Nutrients; nutrition: Nutrition | null; nutrition_source: 'catalog' | 'unknown' | 'menu_reference'; version: number; cancelled_at: string | null; plan_id: string | null; meal_key: string | null; record_group_id?: string | null; skipped_foods?: string[] }

export type MealGroup = { id: string; plan_id: string | null; meal_key: string | null; label: string; eaten_at: string; skipped_foods: string[]; items: Meal[]; nutrients: Nutrients; missing_nutrients: string[] }
