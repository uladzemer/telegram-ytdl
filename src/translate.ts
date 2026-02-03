import OpenAI from "openai"
import { OPENAI_API_KEY } from "./environment"

import { dirname, resolve } from "node:path"
import { fileURLToPath } from "node:url"
import { readJsonFile, writeFileAtomic } from "./file-util"

const __dirname = dirname(fileURLToPath(import.meta.url))

type Translations = Record<string, Record<string, string>>

const SAVED_TRANSLATION_FILE = resolve(
	__dirname,
	"../storage/saved-translations.json",
)

const savedTranslations: Translations = {}
let translationsLoaded = false
let translationsLoadPromise: Promise<void> | null = null

const ensureTranslationsLoaded = async () => {
	if (translationsLoaded) return
	if (!translationsLoadPromise) {
		translationsLoadPromise = (async () => {
			try {
				const data = await readJsonFile<Translations>(
					SAVED_TRANSLATION_FILE,
					{},
					{ label: "saved translations", backupOnError: true },
				)
				Object.assign(savedTranslations, data)
			} catch (error) {
				console.error("Failed to load saved translations:", error)
			} finally {
				translationsLoaded = true
			}
		})()
	}
	await translationsLoadPromise
}

export const translateText = async (text: string, lang: string) => {
	if (OPENAI_API_KEY.trim() === "") return text
	await ensureTranslationsLoaded()

	if (savedTranslations[text]?.[lang]) return savedTranslations[text][lang]

	const client = new OpenAI({ apiKey: OPENAI_API_KEY })

	let translated: string | undefined
	try {
		const response = await client.chat.completions.create({
			model: "gpt-4o-mini",
			messages: [
				{
					role: "system",
					content: `Translate text to the following IETF language tag: ${lang}.
						Keep the HTML formatting. Do not add any other text or explanations`,
				},
				{ role: "user", content: text },
			],
			temperature: 0.2,
			max_tokens: 256,
		})
		const content = response.choices[0]?.message.content
		translated = content ?? undefined
	} catch (error) {
		console.error("Translation request failed:", error)
		return text
	}

	if (!translated) return text

	if (!savedTranslations[text]) savedTranslations[text] = {}
	savedTranslations[text][lang] = translated

	try {
		await writeFileAtomic(
			SAVED_TRANSLATION_FILE,
			JSON.stringify(savedTranslations, undefined, 2),
		)
	} catch (error) {
		console.error("Failed to save translations:", error)
	}

	return translated
}
