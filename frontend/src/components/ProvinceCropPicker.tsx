import type { Options } from '../types'

interface Props {
  options: Options
  province: string // '' means nothing chosen yet
  crop: string
  onProvinceChange: (province: string) => void
  onCropChange: (crop: string) => void
}

// Two dropdowns. The choice lives in App, so the Impact and Simulation tabs share it.
function ProvinceCropPicker({ options, province, crop, onProvinceChange, onCropChange }: Props) {
  return (
    <div className="flex flex-wrap gap-4">
      <label className="flex flex-col text-sm text-gray-500">
        Province
        <select
          value={province}
          onChange={(event) => onProvinceChange(event.target.value)}
          className="mt-1 rounded border bg-white px-3 py-2 text-base text-gray-900"
        >
          {/* Disabled, so the placeholder shows at start but cannot be picked again. */}
          <option value="" disabled>Choose a province</option>
          {options.provinces.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
      <label className="flex flex-col text-sm text-gray-500">
        Crop
        <select
          value={crop}
          onChange={(event) => onCropChange(event.target.value)}
          className="mt-1 rounded border bg-white px-3 py-2 text-base text-gray-900"
        >
          <option value="" disabled>Choose a crop</option>
          {options.crops.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      </label>
    </div>
  )
}

export default ProvinceCropPicker
