import sharp from 'sharp'
import { promises as fs } from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

const SOURCE_ICON = path.join(__dirname, '../src/assets/icon.svg')
const PUBLIC_DIR = path.join(__dirname, '../public')

const PWA_ICONS = [
  {
    size: 192,
    name: 'pwa-192x192.png'
  },
  {
    size: 512,
    name: 'pwa-512x512.png'
  },
  {
    size: 180,
    name: 'apple-touch-icon.png'
  },
  {
    size: 32,
    name: 'favicon.png'
  }
]

async function generateIcons() {
  try {
    // Ensure the public directory exists
    await fs.mkdir(PUBLIC_DIR, { recursive: true })

    // Generate each icon
    for (const icon of PWA_ICONS) {
      await sharp(SOURCE_ICON)
        .resize(icon.size, icon.size)
        .png()
        .toFile(path.join(PUBLIC_DIR, icon.name))
      
      console.log(`Generated ${icon.name}`)
    }

    // Generate maskable icon (with padding)
    await sharp(SOURCE_ICON)
      .resize(512, 512, {
        fit: 'contain',
        background: { r: 29, g: 185, b: 84, alpha: 1 } // #1DB954
      })
      .png()
      .toFile(path.join(PUBLIC_DIR, 'maskable-icon.png'))
    
    console.log('Generated maskable-icon.png')

    // Generate Open Graph image
    await sharp(SOURCE_ICON)
      .resize(1200, 630, {
        fit: 'contain',
        background: { r: 18, g: 18, b: 18, alpha: 1 } // #121212
      })
      .png()
      .toFile(path.join(PUBLIC_DIR, 'og-image.png'))
    
    console.log('Generated og-image.png')

  } catch (error) {
    console.error('Error generating icons:', error)
    process.exit(1)
  }
}

generateIcons() 