import { randomUUID } from "node:crypto"
import { mkdir, readFile, rename, unlink, writeFile } from "node:fs/promises"
import { basename, dirname, join } from "node:path"

type ReadJsonOptions = {
	label?: string
	backupOnError?: boolean
}

const ensureDirForFile = async (filePath: string) => {
	await mkdir(dirname(filePath), { recursive: true })
}

const buildTempPath = (filePath: string) => {
	const dir = dirname(filePath)
	const base = basename(filePath)
	return join(
		dir,
		`.${base}.${process.pid}.${Date.now()}.${randomUUID()}.tmp`,
	)
}

const backupCorruptFile = async (filePath: string) => {
	const dir = dirname(filePath)
	const base = basename(filePath)
	const stamp = new Date().toISOString().replace(/[:.]/g, "-")
	const backupPath = join(dir, `${base}.corrupt.${stamp}`)
	await rename(filePath, backupPath)
}

export const readJsonFile = async <T>(
	filePath: string,
	fallback: T,
	options: ReadJsonOptions = {},
): Promise<T> => {
	try {
		const raw = await readFile(filePath, "utf-8")
		return JSON.parse(raw) as T
	} catch (error) {
		const err = error as NodeJS.ErrnoException
		if (err?.code !== "ENOENT") {
			if (error instanceof SyntaxError && options.backupOnError !== false) {
				backupCorruptFile(filePath).catch(() => {})
			}
			const label = options.label ?? filePath
			console.warn(`Failed to read ${label}:`, error)
		}
		return fallback
	}
}

export const writeFileAtomic = async (filePath: string, content: string) => {
	await ensureDirForFile(filePath)
	const tempPath = buildTempPath(filePath)
	try {
		await writeFile(tempPath, content)
		await rename(tempPath, filePath)
	} catch (error) {
		try {
			await unlink(tempPath)
		} catch {}
		throw error
	}
}
