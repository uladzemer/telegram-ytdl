import { mkdir, readFile, writeFile } from "node:fs/promises"
import { randomUUID } from "node:crypto"
import { ERRORS_FILE, STORAGE_DIR } from "./environment"
import { cutoffWithNotice } from "./util"

export type ErrorLogEntry = {
	id: string
	at: string
	userId?: number
	url?: string
	context?: string
	error?: string
}

const errorLogs: ErrorLogEntry[] = []
let errorLogsLoaded = false
let errorLogsSaveTimer: NodeJS.Timeout | undefined

const ensureStorageDir = async () => {
	try {
		await mkdir(STORAGE_DIR, { recursive: true })
	} catch (error) {
		console.error("Failed to create storage dir:", error)
	}
}

export const loadErrorLogs = async () => {
	if (errorLogsLoaded) return
	errorLogsLoaded = true
	try {
		const raw = await readFile(ERRORS_FILE, "utf-8")
		const data = JSON.parse(raw) as { errors?: ErrorLogEntry[] }
		if (Array.isArray(data?.errors)) {
			errorLogs.push(...data.errors)
		}
	} catch {}
}

const saveErrorLogs = async () => {
	await ensureStorageDir()
	await writeFile(ERRORS_FILE, JSON.stringify({ errors: errorLogs }, null, 2))
}

const scheduleErrorLogsSave = () => {
	if (errorLogsSaveTimer) return
	errorLogsSaveTimer = setTimeout(() => {
		errorLogsSaveTimer = undefined
		saveErrorLogs().catch((error) => {
			console.error("Failed to save error logs:", error)
		})
	}, 2000)
}

export const logErrorEntry = async (
	entry: Omit<ErrorLogEntry, "id" | "at">,
) => {
	await loadErrorLogs()
	errorLogs.unshift({
		id: randomUUID(),
		at: new Date().toISOString(),
		...entry,
		error: entry.error ? cutoffWithNotice(String(entry.error)) : entry.error,
	})
	if (errorLogs.length > 300) errorLogs.length = 300
	scheduleErrorLogsSave()
	saveErrorLogs().catch((error) => {
		console.error("Failed to save error logs:", error)
	})
}

export const getErrorLogs = async () => {
	await loadErrorLogs()
	return errorLogs
}
