# Planned/Existing Features

## API Options

- [ ] Check status (Simple) (Running, Offline, Error)
  - [ ] Overall
  - [ ] Each camera stream
- [ ] Get first image
  - [ ] Date
  - [ ] Time
  - [ ] Day Number
- [ ] Get most recent image
  - [ ] Date
  - [ ] Time
  - [ ] Day Number
- [ ] Get timelapse
  - [ ] With/Without timestamps
  - [ ] Start date
  - [ ] Stop date
  - [ ] Start Time
  - [ ] Stop TimeaZ
- [ ] Timelapse Actions
  - [ ] Start
  - [ ] Stop
  - [ ] Pause
  - [ ] Reset
- [ ] Regenerate timelapse
  - [ ] With/Without timestamps
  - [ ] Start date
  - [ ] Stop date
  - [ ] Start Time
  - [ ] Stop Time
- [ ] Runtime information and statistics
  - Runtime length
  - Images captured
  - Average image size
  - Total image library size

## Config Options / Core functionality options

- [ ] Rotation options
- [ ] Timelapse generation frequency
- [x] delete_images_after_timelapse
- [ ] timelapse_max_images
- [ ] FPS of timelapse. Not sure the best way to designate this. We could do
      something like "one day should be 4 seconds", "12 FPS", or something more
      dynamic like "Video target time is 1 minute, regardless of frames
      captured"

## Processing

I'm breaking down the processing logic into two components: Image processing and
video processing.

## Image processing features (ImageMagick)

- [ ] Detect if image capture returned a black box (common unifi issue)
- [ ] Image color adjustments
- [ ] Image stabalization (I don't know if this is even possible)
  - There is a high probability that, since the camera is outside in nature, at
    some point the camera will get bumped slightly and we'll see a jarring
    effect in the resulting timelapse, so we need a way to compensate for this
    and compare image frames during timelapse generation to make sure we're
    either distoring the images or aligning the images to a common center/track
    point
  - looks like it MAY be possible using
    [vidstab](https://trac.ffmpeg.org/ticket/6816)
  - [This](https://github.com/georgmartius/vid.stab) looks promising but the
    maintainer said he's archiving the project soon
  - After thinking about it, I think it would be outside of FFMPEG's scope for
    this since stablization is done via image stacking instead of encoding. At
    first I thought ImageMagick was going to be the way to go, but
    [this](https://github.com/ImageMagick/ImageMagick/issues/6768) thread said
    they don't have plans to implement stacking alignment and recommended
    [this](https://wiki.panotools.org/Align_image_stack) library instead.
  - I could see us running into an issue where it's aligning image based on
    plant movement/growth so I'm not sure what method we would use to determine
    tracking points?
  - More research links to sift through at some point:
    - <https://usage.imagemagick.org/distorts/#distort_viewport>
    - <https://usage.imagemagick.org/distorts/#control_points>
    - <https://wiki.panotools.org/Align_image_stack>
  - Now I'm thinking about it more and, from a resources standpoint, maybe it
    _is_ better to stabalize the entire video and not get fixated on the idea of
    perfect alignment. If the video is stabalized as a whole and we get a result
    with a slowly moving fluid camera movement, that might be worth the
    processing time/power/resources saved from analyzing each image still in the
    sequence on the fly.

### Video Processing features (FFMPEG)

I'm considering this to be step two. video processing should only be performed
after image processing is complete. Or at a timed interval with a predetermined
objective.

## Investigations

- [ ] I'm working under the assumption that a database would be extreme overkill
      (especially for now), but I'm also wondering if a db might make sense for
      bigger object tracking such as daily checkpoint timelapses. Might be good
      for staying informed about their metadata i.e creation date etc, along
      with their filepaths and relations to the sequence images.

## Future?

- [ ] Backup options
- [ ] Need to figure out a better way to handle nighttime images. Possible noise
      reduction? Topaz api?
- [ ] Notifications

  - [ ] Failure
  - [ ] Warning
    - [ ] Camera connection lost
    - [ ] Low disk space
  - [ ] Status Change
    - [ ] Camera reconnected

- [ ] Offload image processing to remote node
- [ ] UI?! A boy can dream
- [ ] More advanced image filtering/adjustment automations
- [ ] AWS support
